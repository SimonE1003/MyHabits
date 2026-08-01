"""Bilingual (EN/ZH) translation dictionary for MyHabits.

Language is stored in Flask session['lang']. The context processor in
app.py injects t(key) and lang into every template.
"""

TRANSLATIONS = {
    # ---- Navigation ----
    'nav.today':       {'en': 'Today',         'zh': '今日'},
    'nav.set_habits':  {'en': 'Set Habits',    'zh': '设置习惯'},
    'nav.now':         {'en': 'Now',           'zh': '现在'},
    'nav.info':        {'en': 'Info',          'zh': '说明'},
    'nav.logout':      {'en': 'Log Out',       'zh': '登出'},
    'nav.brand':       {'en': 'MyHabits',      'zh': 'MyHabits'},

    # ---- Auth shared ----
    'auth.username':      {'en': 'Username',           'zh': '用户名'},
    'auth.password':      {'en': 'Password',           'zh': '密码'},
    'auth.confirm':       {'en': 'Confirm',            'zh': '确认密码'},
    'auth.username_ph':   {'en': 'Username',           'zh': '用户名'},
    'auth.login_btn':     {'en': 'Log In',             'zh': '登录'},
    'auth.register_btn':  {'en': 'Create Account',     'zh': '创建账户'},
    'auth.tag_login':     {'en': 'start your trajectory',  'zh': '开启你的轨迹'},
    'auth.tag_register':  {'en': 'Begin the trajectory.',   'zh': '开启你的轨迹。'},
    'auth.new_here':      {'en': 'New here?',          'zh': '新用户？'},
    'auth.create_link':   {'en': 'Create an account',  'zh': '创建账户'},
    'auth.have_account':  {'en': 'Already have an account?', 'zh': '已有账户？'},
    'auth.login_link':    {'en': 'Log in',             'zh': '登录'},

    # ---- Login errors ----
    'login.error_both':   {'en': 'Please enter both username and password.',   'zh': '请输入用户名和密码。'},
    'login.error_match':  {'en': "That username and password don't match.",    'zh': '用户名和密码不匹配。'},

    # ---- Register errors ----
    'register.error_both':    {'en': 'Please enter both username and password.',  'zh': '请输入用户名和密码。'},
    'register.error_match':   {'en': "Those passwords don't match.",              'zh': '两次密码不一致。'},
    'register.error_taken':   {'en': 'That username is already taken.',           'zh': '该用户名已被占用。'},
    'register.error_length':  {'en': 'Username or password is too long.',         'zh': '用户名或密码过长。'},

    # ---- Today page (empty / not started) ----
    'today.empty_eyebrow': {'en': 'No active challenge',  'zh': '暂未开始挑战'},
    'today.empty_lede':    {'en': 'You have not yet started a challenge.', 'zh': '你还没有开始挑战。'},
    'today.empty_desc':    {
        'en': 'Define your six habits and begin the 21-day trajectory. Small marks, accumulated daily, follow the path.',
        'zh': '定义你的六个习惯，开启 21 天轨迹。每日点滴积累，终会走出这条路。'
    },
    'today.empty_btn':     {'en': 'Set Your Habits',  'zh': '设置习惯'},

    # ---- Today page (active) ----
    'today.started':       {'en': 'Started',          'zh': '开始于'},
    'today.pct_complete':  {'en': 'complete',         'zh': '已完成'},
    'today.days_remaining': {'en': 'days remaining',  'zh': '天剩余'},
    'today.morning':       {'en': 'Morning',          'zh': '上午'},
    'today.afternoon':     {'en': 'Afternoon',        'zh': '下午'},
    'today.evening':       {'en': 'Evening',          'zh': '晚上'},
    'today.done':          {'en': 'Done',             'zh': '已完成'},
    'today.mark':          {'en': 'Mark',             'zh': '标记'},
    'today.confirm_done':  {'en': 'Mark this habit as done?', 'zh': '将此习惯标记为已完成？'},
    'today.network_error': {'en': 'Network error. Please check your connection.', 'zh': '网络错误，请检查连接。'},
    'today.failed_update': {'en': 'Failed to update. Please reload.', 'zh': '更新失败，请刷新页面。'},

    # ---- Today page (finished) ----
    'today3.eyebrow':      {'en': 'Challenge complete',  'zh': '挑战完成'},
    'today3.lede':         {'en': 'Twenty-one days, mapped.', 'zh': '二十一天，已完成。'},
    'today3.desc':         {
        'en': 'Below is your completion record. Use it to see which habits are forming strongly and which need another cycle.',
        'zh': '以下是你的完成记录。看看哪些习惯已经稳固，哪些还需要再来一轮。'
    },
    'today3.tip_title':    {'en': 'If this is your first cycle', 'zh': '如果是你的第一个周期'},
    'today3.tip1':         {'en': 'Consider taking the next 21 days to track the same six habits.', 'zh': '考虑用接下来的 21 天继续追踪同样的六个习惯。'},
    'today3.tip2':         {'en': 'This reveals which habits are forming strongly and which are not.', 'zh': '这样可以看出哪些习惯已稳固，哪些还不够。'},
    'today3.tip3':         {'en': 'Use the report to swap one strong habit for a new one you want to form.', 'zh': '根据报告，用一个已稳固的习惯换一个想培养的新习惯。'},
    'today3.btn':          {'en': 'Start a New 21-Day Challenge', 'zh': '开始新的 21 天挑战'},
    'today3.confirm':      {'en': 'Starting a new challenge will reset all current progress. Continue?', 'zh': '开始新挑战会重置当前所有进度，确定继续吗？'},

    # ---- Set Habits page ----
    'set_habits.eyebrow':  {'en': 'Step 01 · Define',  'zh': '第 01 步 · 定义'},
    'set_habits.lede':     {
        'en': 'Choose six habits.\nBracket them into three phases of day.',
        'zh': '选择六个习惯，\n将它们分到一天中的三个时段。'
    },
    'set_habits.desc':     {
        'en': 'Aim for habits you can sustain. Four or five completions per day is enough — six is the ceiling, not the requirement.',
        'zh': '选择你能坚持的习惯。每天完成四到五个就足够了——六个是上限，不是硬性要求。'
    },
    'set_habits.placeholder': {'en': 'Habit',  'zh': '习惯'},
    'set_habits.phase':    {'en': 'Phase',     'zh': '时段'},
    'set_habits.btn':      {'en': 'Begin 21-Day Challenge', 'zh': '开始 21 天挑战'},
    'set_habits.confirm':  {'en': 'This will reset all progress. Continue?', 'zh': '这会重置所有进度，确定继续吗？'},
    'set_habits.error_no_habit': {'en': 'You need at least one habit', 'zh': '至少需要填写一个习惯'},
    'set_habits.error_no_phase': {'en': 'please enter a Time Phase for each habit', 'zh': '请为每个习惯选择时段'},
    'set_habits.timezone': {'en': 'Your timezone', 'zh': '你的时区'},
    'set_habits.timezone_desc': {
        'en': 'Used to calculate your daily cutoff. Pick where you currently live.',
        'zh': '用于计算你每天的习惯打卡截止时间。选择你目前所在的地区。'
    },

    # ---- Now page ----
    'now.lede':            {'en': 'What remains undone today?', 'zh': '今天还剩什么没做？'},
    'now.habits_left':     {'en': 'habit',   'zh': '个习惯'},  # used as "N habits left"
    'now.habits_left_pl':  {'en': 'habits',  'zh': '个习惯'},
    'now.left':            {'en': 'left',    'zh': '未完成'},
    'now.bedtime_label':   {'en': "Tonight's bedtime", 'zh': '今晚几点睡'},
    'now.btn':             {'en': 'What to do now',   'zh': '现在该做什么'},
    'now.thinking':        {'en': 'Thinking…',        'zh': '思考中…'},
    'now.generated':       {'en': 'Generated',        'zh': '生成用时'},
    'now.network_error':   {'en': 'Network error',    'zh': '网络错误'},

    # ---- Now result page (edge cases) ----
    'now_result.no_habits_eyebrow': {'en': 'No habits yet',  'zh': '尚未设置习惯'},
    'now_result.no_habits_lede':    {'en': 'Start by defining your habits.', 'zh': '先定义你的习惯。'},
    'now_result.no_habits_desc':    {
        'en': "You haven't set any habits yet. Define your six habits to begin the 21-day trajectory.",
        'zh': '你还没有设置任何习惯。定义你的六个习惯，开启 21 天轨迹。'
    },
    'now_result.no_habits_btn':     {'en': 'Set Your Habits', 'zh': '设置习惯'},

    'now_result.not_started_eyebrow': {'en': 'Not started',  'zh': '未开始'},
    'now_result.not_started_lede':    {'en': "Your challenge hasn't begun.", 'zh': '你的挑战尚未开始。'},
    'now_result.not_started_desc':    {
        'en': "Set your habits to start the 21-day trajectory. Once you're in, come back here to plan each evening.",
        'zh': '设置习惯即可开启 21 天轨迹。开始后，每晚回来这里规划时间。'
    },
    'now_result.not_started_btn':     {'en': 'Set Your Habits', 'zh': '设置习惯'},

    'now_result.finished_eyebrow': {'en': 'Challenge complete', 'zh': '挑战完成'},
    'now_result.finished_lede':    {'en': '21 days. Done.', 'zh': '21 天，已完成。'},
    'now_result.finished_desc':    {
        'en': 'This round is over. Set a new set of habits to start another 21-day trajectory.',
        'zh': '本轮已结束。设置新的习惯，开启下一轮 21 天轨迹。'
    },
    'now_result.finished_btn':     {'en': 'Start a New Round', 'zh': '开始新一轮'},
    'now_result.back_today':       {'en': 'Back to Today',     'zh': '返回今日'},

    'now_result.all_done_eyebrow': {'en': 'All clear',    'zh': '全部完成'},
    'now_result.all_done_lede':    {'en': 'Today is complete.', 'zh': '今天已全部完成。'},
    'now_result.all_done_desc':    {'en': 'Nothing left. Rest well and return tomorrow.', 'zh': '没有待办了。好好休息，明天再来。'},

    # ---- Info page ----
    'info.eyebrow':        {'en': 'Field guide',  'zh': '使用指南'},
    'info.lede':           {
        'en': 'A protocol for the next twenty-one days.',
        'zh': '接下来二十一天的方案。'
    },
    'info.procedure':      {'en': 'Procedure', 'zh': '步骤'},
    'info.proc1':          {'en': 'Think about six habits you want to form — ones you can do consistently.', 'zh': '想想你想培养的六个习惯——你能坚持去做的那些。'},
    'info.proc2':          {'en': 'Bracket those into three time phases: morning, afternoon, evening.', 'zh': '将它们分到三个时段：上午、下午、晚上。'},
    'info.proc3':          {'en': 'Go to the Set Habits page to start your 21-day challenge.', 'zh': '前往"设置习惯"页面开启你的 21 天挑战。'},
    'info.proc4':          {'en': 'Aim to complete 4–5 habits every day. Six is great, but not required.', 'zh': '每天力争完成 4–5 个习惯。六个很好，但不是硬性要求。'},
    'info.proc5':          {'en': "If you miss some habits, don't compensate the next day. Just focus on completing 4–5 the day after.", 'zh': '如果漏了几个习惯，不要第二天补偿。专注于第二天完成 4–5 个就好。'},
    'info.proc6':          {'en': 'The result will appear in the Today page after 21 days.', 'zh': '21 天后，结果会出现在"今日"页面。'},
    'info.sample':         {'en': 'Sample habits', 'zh': '习惯示例'},
    'info.sample_desc':    {
        'en': 'Below are habits that anyone could benefit from — cost-free and rooted in science and biology. The time phases are reference only; you can still benefit from performing a habit in a different phase.',
        'zh': '以下是人人皆可受益的习惯——不花一分钱，有科学和生物学依据。时段仅供参考，在其他时段做也同样有益。'
    },
    'info.morning':        {'en': 'Morning', 'zh': '上午'},
    'info.morning_desc':   {'en': 'Alert and focused state. Action and focus oriented.', 'zh': '清醒专注的状态。适合行动与专注。'},
    'info.afternoon':      {'en': 'Afternoon', 'zh': '下午'},
    'info.afternoon_desc': {'en': 'Highest serotonin. Relaxed state of being.', 'zh': '血清素最高。放松的状态。'},
    'info.evening':        {'en': 'Evening', 'zh': '晚上'},
    'info.evening_desc':   {'en': 'Relax and prepare for sleep.', 'zh': '放松，准备入睡。'},
    'info.science':        {'en': 'Science behind the site', 'zh': '背后的科学'},
    'info.habit_sunlight': {'en': 'Sunlight viewing for 5–20 min', 'zh': '晒太阳 5–20 分钟'},
    'info.habit_hardwork': {'en': 'Hard work for 1.5h', 'zh': '高强度工作 1.5 小时'},
    'info.habit_visualize':{'en': 'Visualize the day (reduces limbic friction)', 'zh': '想象今天一天（降低边缘系统阻力）'},
    'info.habit_cold':     {'en': 'Cold exposure (cold shower)', 'zh': '冷暴露（冷水澡）'},
    'info.habit_exercise': {'en': 'Physical exercise', 'zh': '体育锻炼'},
    'info.habit_meditation':{'en': 'Meditation', 'zh': '冥想'},
    'info.habit_brainstorm':{'en': 'Brainstorming', 'zh': '头脑风暴'},
    'info.habit_talk':     {'en': 'Talking to loved ones', 'zh': '和爱的人聊天'},
    'info.habit_reading':  {'en': 'Reading', 'zh': '阅读'},
    'info.habit_journal':  {'en': 'Journaling', 'zh': '写日记'},
    'info.habit_nsdr':     {'en': 'NSDR (non-sleep deep rest)', 'zh': 'NSDR（非睡眠深度休息）'},
    'info.habit_dim':      {'en': 'Dim the lights', 'zh': '调暗灯光'},

    # ---- Apology / error page ----
    'apology.title':       {'en': 'Something went wrong', 'zh': '出了一点问题'},
    'apology.back':        {'en': 'Go back', 'zh': '返回'},

    # ---- Logout ----
    'logout.confirm':      {'en': 'Log out of MyHabits?', 'zh': '确定登出 MyHabits？'},

    # ---- Quotes (today page) ----
    'quote.1': {'en': 'Up to 70% of our waking behaviors are made up of habitual behaviors. — Andrew Huberman',
                'zh': '我们清醒时高达 70% 的行为都是习惯性行为。——安德鲁·休伯曼'},
    'quote.2': {'en': 'A slight change in your daily habits can guide your life to a very different destination - James Clear',
                'zh': '日常习惯的微小改变，会将你的人生引向截然不同的终点。——詹姆斯·克利尔'},
    'quote.3': {'en': 'Forget about goals, focus on systems instead - James Clear',
                'zh': '忘掉目标，专注于系统。——詹姆斯·克利尔'},
    'quote.4': {'en': 'Goals are good for setting a direction, but systems are best for making progress - James Clear',
                'zh': '目标用于确定方向，系统才能带来进步。——詹姆斯·克利尔'},
    'quote.5': {'en': 'Until you make the unconscious conscious, it will direct your life and you will call it fate - Carl Jung',
                'zh': '当你尚未让无意识变为意识时，它将主宰你的一生，而你会称之为命运。——卡尔·荣格'},
    'quote.6': {'en': 'Environment is the invisible hand that shapes human behavior - James Clear',
                'zh': '环境是塑造人类行为的无形之手。——詹姆斯·克利尔'},
    'quote.7': {'en': 'Stay Hard! - David Goggins',
                'zh': '坚持硬核！——大卫·戈金斯'},
    'quote.8': {'en': 'Discipline Equals Freedom - Jocko Willink',
                'zh': '纪律即自由。——乔科·威林克'},

    # ---- Language switcher ----
    'lang.label':          {'en': 'Language', 'zh': '语言'},

    # ---- Stats page ----
    'nav.stats':           {'en': 'Stats',           'zh': '数据'},
    'stats.title':         {'en': 'Stats',           'zh': '数据'},
    'stats.eyebrow':       {'en': 'Your trajectory', 'zh': '你的轨迹'},
    'stats.lede':          {'en': 'How you are building yourself.', 'zh': '你正在如何塑造自己。'},
    'stats.desc':          {
        'en': 'A multi-dimensional view of your discipline across all challenge rounds.',
        'zh': '跨越所有挑战轮次的执行力多维度视图。'
    },
    'stats.completions':   {'en': 'completions',     'zh': '次完成'},
    'stats.day_streak':    {'en': 'day streak',      'zh': '天连续'},
    'stats.days':          {'en': 'days',            'zh': '天'},
    'stats.full_days':     {'en': 'full days',       'zh': '全勤天'},
    'stats.pts':           {'en': 'pts',             'zh': '分'},
    'stats.insufficient':  {'en': 'Not enough data yet — keep going for a meaningful score.', 'zh': '数据不足——继续坚持才能得到有意义的分数。'},

    # Score levels
    'stats.level_master':       {'en': 'Mastery',          'zh': '精通'},
    'stats.level_disciplined':  {'en': 'Disciplined',      'zh': '自律'},
    'stats.level_consistent':   {'en': 'Consistent',       'zh': '稳定'},
    'stats.level_building':     {'en': 'Building',         'zh': '建设中'},
    'stats.level_beginning':    {'en': 'Beginning',        'zh': '起步'},

    # Dimensions
    'stats.dim_completion': {'en': 'Completion',     'zh': '完成率'},
    'stats.dim_streak':     {'en': 'Streak',         'zh': '连续性'},
    'stats.dim_recovery':   {'en': 'Recovery',       'zh': '恢复力'},
    'stats.dim_momentum':   {'en': 'Momentum',       'zh': '趋势'},
    'stats.last_7_vs_prev': {'en': 'Last 7 vs prior 7', 'zh': '近7天 vs 前7天'},

    # Heatmap
    'stats.heatmap_title': {'en': 'Activity calendar', 'zh': '活动日历'},
    'stats.heatmap_desc':  {
        'en': 'Each square is a day. Darker means more habits completed.',
        'zh': '每个方块代表一天。颜色越深表示完成的习惯越多。'
    },
    'stats.less':          {'en': 'Less',  'zh': '少'},
    'stats.more':          {'en': 'More',  'zh': '多'},

    # Rounds
    'stats.rounds_title':  {'en': 'Challenge history', 'zh': '挑战历史'},
    'stats.round':         {'en': 'Round',  'zh': '第轮'},
    'stats.current':       {'en': 'Current', 'zh': '当前'},

    # Per-habit detail
    'stats.habit_detail':  {'en': 'Habit breakdown', 'zh': '习惯详情'},

    # Empty state
    'stats.empty_eyebrow': {'en': 'No data yet', 'zh': '暂无数据'},
    'stats.empty_lede':    {'en': 'Your stats appear once you start.', 'zh': '开始挑战后，数据将出现在这里。'},
    'stats.empty_desc':    {
        'en': 'Set your habits and begin the 21-day challenge to see your discipline metrics here.',
        'zh': '设置习惯并开始 21 天挑战，你的执行力数据将在这里呈现。'
    },
    'stats.empty_btn':     {'en': 'Set Your Habits', 'zh': '设置习惯'},
}


def t(key, lang='en'):
    """Translate a key into the given language. Falls back to English,
    then to the key itself if not found."""
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    return entry.get(lang, entry.get('en', key))


# Quote keys in order (matches the random.choice pattern in app.py)
QUOTE_KEYS = [f'quote.{i}' for i in range(1, 9)]
