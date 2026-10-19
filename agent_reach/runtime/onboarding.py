"""Read-only session discovery and explicit connection choices. Never logs a user in."""
import json
import urllib.request
from urllib.parse import urlsplit

from agent_reach.config import Config
from agent_reach.utils.url import host_matches

from . import state
from .result import BAD_INPUT, NEED_SETUP, ReachError

# These describe public routes an agent can try, not authenticated Reach readiness.
# A successful sample depends on the tool, network exit, content and platform response.
_PUBLIC_ACCESS = {
    'web': '先用 Agent 已有网页搜索和读取；只为剩余缺口调用 Reach。',
    'github': '公开仓库、README、Issue/PR 及公开评论可先用网页或公开接口。',
    'youtube': '公开搜索、简介可先读；原生工具的部分样本可取评论、字幕和时间戳。',
    'bilibili': '公开搜索、简介、统计可先读；部分公开接口可取评论及回复关系。',
    'v2ex': '公开主题正文和部分回复可先读；完整性、分页需要单独核对。',
    'reddit': '公开搜索、正文和部分评论可先读；部分公开 JSON 样本可含评论及 parent_id。',
    'twitter': '公开搜索摘要、部分单帖全文可先尝试；公开嵌入不提供评论流。',
    'xiaohongshu': '公开发现页可能提供笔记 ID 和作者；不据此认定正文、评论可读。',
    'instagram': '公开搜索或主页信息可先尝试；HTML 可能只有应用外壳，Caption 和评论未获统一验证。',
    'facebook': '公开搜索摘要可先尝试；帖子正文和评论取决于页面与访问路径。',
    'linkedin': '公开职位搜索和职位页可先尝试；本轮未做匿名粒度验收。',
    'boss': '公开职位索引和页面可先尝试；本轮未做匿名粒度验收。',
    'xueqiu': '公开股票行情和名称搜索可先尝试；社区内容另按所选路径判断。',
}

_CAPABILITY_LIMITS = {
    'youtube': ['read 返回元信息和简介；没有独立 comments 动作。',
                '字幕依赖可用轨道；转录还需配置服务及额度，登录不保证有字幕。'],
    'bilibili': ['read 返回元信息和简介；没有独立 comments 动作。',
                 'Reach subtitle 路径可能要求登录，且视频须有可用字幕。'],
    'reddit': ['read 仅承诺其返回的帖子和评论；不保证完整评论树，不提供发评论动作。'],
    'twitter': ['thread 仅覆盖实际返回的回复；不保证完整评论流，不提供发帖动作。'],
    'xiaohongshu': ['只报告实际读取的正文、已加载评论和回复，不承诺完整导出。'],
    'instagram': ['search 搜索用户；没有任意帖子 read 或独立 comments 动作。'],
    'facebook': ['当前仅声明 search/profile，不承诺独立帖文读取或评论导出。'],
    'linkedin': ['当前仅声明职位搜索和 JD 读取，不承诺联系人或动态抓取。'],
    'boss': ['当前仅声明职位搜索和 JD 读取；登录不保证平台始终允许访问。'],
    'v2ex': ['回复是否完整须核对分页与实际返回数量。'],
}


# Capability depth is separate from installation and live-check status.
# Standalone native/API evidence must not masquerade as a declared Reach action.
_ANONYMOUS_DEPTH = {
    'github': ('✅ 仓库搜索', '✅ README、Issue/PR 正文', '✅ 公开 Issue/PR 评论', '—'),
    'youtube': ('✅ 视频搜索', '✅ 简介；不等同视频内容',
                '⚠️ 原生工具样本可读；❌ Reach 无独立评论动作', '✅ 已有字幕；⚙️ 音频转录需服务 Key'),
    'bilibili': ('✅ 视频搜索、热门', '✅ 简介、元信息；不等同视频内容',
                 '⚠️ 公开接口样本可读；❌ Reach 无独立评论动作', '🔐 Reach 字幕路径按需登录；须有字幕'),
    'v2ex': ('✅ 热门、节点列表', '✅ 主题正文', '⚠️ 返回的回复；完整性需核对', '—'),
    'web': ('✅ 网页搜索', '⚠️ 可公开读取的正文', '⚠️ 仅页面已返回的评论', '❌ 无独立字幕动作'),
}

_DISPLAY_NAMES = {
    'github': 'GitHub', 'youtube': 'YouTube', 'bilibili': 'B站', 'v2ex': 'V2EX',
    'web': 'Web', 'reddit': 'Reddit', 'twitter': 'X/Twitter', 'facebook': 'Facebook',
    'instagram': 'Instagram', 'xiaohongshu': '小红书', 'linkedin': 'LinkedIn',
    'boss': 'BOSS直聘', 'xueqiu': '雪球',
}

_ACTION_NAMES = {
    'search': '搜索', 'read': '详情读取', 'subreddit': '板块帖子列表',
    'profile': '个人主页', 'tweets': '用户推文', 'thread': '推文串',
    'posts': '指定用户帖子', 'comments': '评论读取', 'jobs': '职位搜索',
    'hot_posts': '热门帖子', 'hot_stocks': '热门股票',
}

_STATUS_LABELS = {
    'not_added': '未接入，可按需添加', 'needs_setup': '待配置', 'unverified': '已接入，待实测',
    'ready': '已有有效验收', 'search_ready': '仅搜索已有验收',
    'needs_login': '所测动作要求登录', 'cooldown': '暂缓访问',
    'needs_user_action': '等待人工验证', 'broken': '当前路径故障',
}


def installation_report(result):
    """Render the complete install receipt, without discovery or network access."""
    def cell(value):
        return str(value).replace('|', r'\|').replace('\n', ' ')

    entries = result['capability_summary']['channels']
    installs = {row['channel']: row for row in result['default_channels']}
    installed = sum(bool(row['ok']) for row in installs.values())
    lines = [
        f"# Agent Reach {result['version']} · 安装与能力清单", '',
        f'默认渠道依赖：{installed}/{len(installs)} 项准备成功。安装结果与联网验收分别列出。', '',
        '✅ 提供免登录路径；⚠️ 部分内容或受访问条件影响；🔐 该路径按需登录；'
        '⚙️ 需要额外配置；❌ 本版未提供相应动作；— 不适用。',
        '表中勾叉表示能力范围，不表示本机已经联网测通；公开路径可能使用 Agent 自带工具、原生工具或公开接口。', '',
        '## 默认渠道：安装结果与免登录粒度', '',
        '| 渠道 | 本次安装 | 搜索/列表 | 正文/详情 | 评论/回复 | 字幕/转录 |',
        '|---|---|---|---|---|---|',
    ]
    for entry in entries:
        if entry['level'] != 'default':
            continue
        name = entry['channel']
        item = installs.get(name)
        status = ('已安装' if item['ok'] else
                  '安装失败：' + item.get('error', {}).get('code', 'UNKNOWN')) if item else '保留用户移除'
        depth = _ANONYMOUS_DEPTH.get(name, ('⚠️ 以声明动作与实际返回为准',) * 4)
        lines.append('| ' + ' | '.join(map(cell, (_DISPLAY_NAMES.get(name, name), status, *depth))) + ' |')
    lines += [
        '', '## 按需渠道：公开可读与登录后的增量', '',
        '| 渠道 | 当前接入 | 免登录先尝试 | 按需登录/配置后可启用 | 当前边界 |',
        '|---|---|---|---|---|',
    ]
    for entry in entries:
        if entry['level'] == 'default':
            continue
        name = entry['channel']
        actions = entry['authentication']['may_enable_actions']
        labels = [_ACTION_NAMES.get(action, action) for action in actions]
        if name == 'instagram':
            labels = ['用户搜索' if action == 'search' else label for action, label in zip(actions, labels)]
        elif name == 'reddit':
            labels = ['帖子及返回评论' if action == 'read' else label for action, label in zip(actions, labels)]
        elif name == 'boss':
            labels = ['职位搜索' if action == 'search' else label for action, label in zip(actions, labels)]
        extra = ('🔐 ' + '、'.join(labels) + '（该路径要求认证时）') if actions else '⚙️ 按声明动作配置'
        lines.append('| ' + ' | '.join(map(cell, (
            _DISPLAY_NAMES.get(name, name), _STATUS_LABELS.get(entry['reach_status'], entry['reach_status']),
            '⚠️ ' + entry['public_access'], extra, ' '.join(entry['limits']) or '仅覆盖实际返回内容',
        ))) + ' |')
    lines += ['', '**本机联网验收**：本次安装没有发起平台查询。已存在且仍有效的验收如下；其余待实测。']
    verified = [entry for entry in entries if entry['verified_actions']]
    lines += ['- ' + _DISPLAY_NAMES.get(entry['channel'], entry['channel']) + '：' +
              ' / '.join(entry['verified_actions']) for entry in verified] if verified else ['- 暂无有效动作验收记录。']
    lines += [
        '', '**Reddit 怎么用**：⚠️ 先尝试公开搜索、正文和部分评论，公开 JSON 样本可能含父子 ID；'
        '🔐 需要时启用站内搜索、板块列表及帖子/返回评论读取；'
        '❌ 不提供发评论；⚠️ 完整评论树与全部回复不作保证，登录后仍需实际验证。', '',
        '直接告诉我你想查什么即可。已有公开结果够用就交付；缺少某项内容时再准备渠道、复用授权会话，实际需要时才请你登录。',
    ]
    return '\n'.join(lines) + '\n'


def capability_summary(channels, statuses):
    """Describe public options, declared actions and local evidence without any I/O.

    Management supplies status records so this summary cannot initiate discovery,
    installation, login or a live request. Actions always come from the registry.
    """
    by_name = {entry['channel']: entry for entry in statuses}
    entries = []
    for ch in channels:
        current = by_name.get(ch.name, {})
        names = [action.name for action in ch.actions]
        can_login = bool(ch.login_url or ch.login_argv)
        auth_actions = {'bilibili': ['subtitle'], 'xueqiu': ['hot_posts', 'hot_stocks']}.get(
            ch.name, names if can_login else [])
        entries.append({
            'channel': ch.name,
            'level': ch.level,
            'reach_status': current.get('status', 'unverified'),
            'verified_actions': current.get('verified_actions', []),
            'actions': [{'action': action.name, 'detail': action.help} for action in ch.actions],
            'public_access': _PUBLIC_ACCESS.get(ch.name, '先尝试 Agent 已有公开搜索和读取。'),
            'authentication': {
                'when': 'only_if_required',
                'may_enable_actions': [name for name in auth_actions if name in names],
                'note': '剩余任务的选定路径实际要求认证时，先复用已授权会话，再请用户登录；登录后仍需验证动作。',
            },
            'limits': _CAPABILITY_LIMITS.get(ch.name, []),
        })
    message = ['先使用 Agent 已有公开搜索和读取；Reach 按需补充能力，安装不要求逐个平台登录。']
    for entry in entries:
        actions = '/'.join(action['action'] for action in entry['actions'])
        status_label = _STATUS_LABELS.get(entry['reach_status'], entry['reach_status'])
        limits = ' '.join(entry['limits'])
        message.append(f"{entry['channel']}：{entry['public_access']} Reach {actions}（{status_label}）。{limits}")
    return {
        'policy': 'public_first; login_only_for_remaining_task_when_required',
        'evidence_note': '公开路径说明来自样本与访问条件，不能代替本机 Reach 验收；网络、403、超时或验证码均不能单独证明需要登录。',
        'channels': entries,
        'message': '\n'.join(message),
    }


def cdp_url():
    value = Config(read_only=True).get('boss_cdp_url', 'http://127.0.0.1:9222')
    return validate_cdp(value)


def validate_cdp(value):
    try:
        u = urlsplit(value)
        valid = (u.scheme == 'http' and u.hostname in {'localhost', '127.0.0.1', '::1'}
                 and u.port and not u.username and not u.password and not u.query
                 and not u.fragment and u.path in ('', '/'))
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ReachError(BAD_INPUT, 'CDP must be a loopback HTTP address with an explicit port')
    return value.rstrip('/')


def cdp_status():
    url = cdp_url()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + '/json/list', timeout=2) as resp:
            tabs = json.loads(resp.read(1024 * 1024))
        found = isinstance(tabs, list) and any(
            isinstance(t, dict) and t.get('type') == 'page'
            and host_matches(t.get('url', ''), 'zhipin.com') for t in tabs)
        return {'endpoint': url, 'connected': isinstance(tabs, list), 'boss_tab_present': bool(found)}
    except (OSError, ValueError):
        return {'endpoint': url, 'connected': False, 'boss_tab_present': False}


def require_boss_cdp():
    status = cdp_status()
    if not status['connected'] or not status['boss_tab_present']:
        raise ReachError(NEED_SETUP, 'No existing BOSS page on the selected CDP endpoint',
                         hint='Run agent-reach login boss for reuse options; only --new-browser opens a dedicated browser.')
    return status['endpoint']


def bind_cdp(value):
    value = validate_cdp(value)
    Config().set('boss_cdp_url', value)
    data = state.load()
    data['checks'].pop('boss', None)
    state.save(data)
    return {'channel': 'boss', 'cdp_url': value, 'verified': False}


def profiles():
    from .browser import connected_contexts
    from .result import ReachError
    from .tools import resolve
    if not resolve('opencli'):
        return {'profiles': [], 'discovery_error': 'OpenCLI is not installed'}
    try:
        contexts = connected_contexts()
    except ReachError as exc:
        return {'profiles': [], 'discovery_error': exc.message}
    labels = Config(read_only=True).get('browser_labels', {})
    return {'profiles': [{'id': c, 'label': labels.get(c, c), 'connected': True} for c in contexts]}


def use_profile(value, label=None):
    from .browser_binding import KEY
    if value not in [p['id'] for p in profiles()['profiles']]:
        raise ReachError(NEED_SETUP, 'Selected profile is not connected; reconnect its OpenCLI extension first')
    config = Config()
    config.set('browser_default_profile', value)
    if label:
        labels = dict(config.get('browser_labels', {}))
        labels[value] = label
        config.set('browser_labels', labels)
    data = state.load()
    overrides = config.get(KEY, {})
    from agent_reach.channels import get_all_channels
    for ch in get_all_channels():
        if 'opencli' in ch.tools and ch.name not in overrides:
            data['checks'].pop(ch.name, None)
            for action in data.get('backend_health', {}).get(ch.name, {}).values():
                action.pop('opencli', None)
    state.save(data)
    return {'profile': value, 'scope': 'OpenCLI channels without a per-channel override', 'verified': False}


def session_plan(ch):
    """Describe transport availability separately from authentication and saved checks."""
    from agent_reach.backends.opencli import OPENCLI_EXTENSION_URL

    from .browser_binding import profile_for
    from .sessions import has_login_state
    plan = {'channel': ch.name, 'logged_in': None, 'opened_browser': False,
            'last_check': state.load()['checks'].get(ch.name),
            'verify': f'agent-reach check {ch.name} --search'}
    if 'opencli' in ch.tools:
        profile = profile_for(ch.name)
        found = profiles()
        if profile == 'dedicated':
            from . import browser
            context = browser.bound_context()
        else:
            context = profile
        connected = context is not None and context in [p['id'] for p in found['profiles']]
        plan.update({'via': 'opencli', 'profile': profile, 'connected': connected, 'extension_url': OPENCLI_EXTENSION_URL, **found,
                     'next': ('Existing browser selected. Verify first; log in there only if NEED_LOGIN.' if connected
                              else 'Choose/reconnect an existing browser: agent-reach browser profiles; agent-reach browser use CONTEXT_ID. No browser has been opened.')})
    elif ch.name == 'boss':
        status = cdp_status()
        plan.update({'via': 'cdp', **status,
                     'next': ('Existing BOSS page found. Confirm it is logged in and stable; then login boss --sync and check boss --search.'
                              if status['boss_tab_present'] else
                              'Use browser bind boss http://127.0.0.1:PORT for an existing CDP browser. Ordinary Chrome without CDP cannot be attached. Only login boss --new-browser explicitly opens the persistent dedicated profile.')})
    else:
        saved = bool(ch.session and has_login_state(ch.session))
        plan.update({'via': 'native-tool', 'saved_state_present': saved,
                     'next': 'Verify the existing tool/session first. Only use login CHANNEL --native if authentication is needed; its tool may open a browser or show a QR code.'})
    from .manage import uses_cloak
    if uses_cloak(ch):
        from agent_reach.backends.cloak import status as cloak_status
        plan['primary_backend'] = cloak_status(ch.name)
        plan['fallback_next'] = plan['next']
        plan['next'] = (f"Run agent-reach ensure {ch.name} to check the existing Cloak or connected "
                        "OpenCLI session. To authorize site-scoped import from Chrome, add "
                        "--reuse-profile ID. The user logs in only when ensure requests it.")
    return plan


def open_boss_browser():
    """Explicit opt-in only; retain profile, never close/restart a user's browser."""
    import subprocess

    from . import browser
    status = cdp_status()
    if status['connected']:
        return {**status, 'opened_browser': False, 'next': 'Use the existing window; open BOSS there if needed and confirm login.'}
    if cdp_url() != 'http://127.0.0.1:9222':
        raise ReachError(NEED_SETUP, 'Reconnect the selected CDP browser; refusing to launch a different endpoint')
    from agent_reach.utils.paths import make_private_dir
    make_private_dir(browser.profile_dir())
    subprocess.Popen([browser.ensure_chrome(), '--remote-debugging-address=127.0.0.1',
                      '--remote-debugging-port=9222', f'--user-data-dir={browser.profile_dir()}',
                      'https://www.zhipin.com/web/geek/job'], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    if not browser.wait_for(lambda: cdp_status()['connected'], 25, interval=0.5):
        raise ReachError(NEED_SETUP, 'Dedicated CDP browser did not become ready; no profile was deleted')
    return {'opened_browser': True, 'profile_reused': True, 'logged_in': None,
            'next': 'Confirm this window is logged in and stable, then agent-reach login boss --sync.'}
