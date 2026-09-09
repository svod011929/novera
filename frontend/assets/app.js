(() => {
  'use strict';
  // NOVERA V9.4 native account isolation

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  // NOVERA V10 per-account Telegram SecureStorage authentication
  // NOVERA V10.1 admin inviter management
  // NOVERA V10.2 real admin treasury test payouts
  // NOVERA V10.3 Telegram bot + in-app notification center
  const qs = new URLSearchParams(window.location.search);
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>'"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const money = (minor) => (Number(minor || 0) / 1000000).toFixed(2);
  const percent = (bps) => `${(Number(bps || 0) / 100).toFixed(Number(bps || 0) % 100 ? 1 : 0)}%`;
  const fmtDate = (ts) => ts ? new Date(Number(ts) * 1000).toLocaleString([], {day:'2-digit',month:'2-digit',year:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—';
  const fmtShort = (ts) => ts ? new Date(Number(ts) * 1000).toLocaleString([], {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—';
  const compactAddress = (value) => value && value.length > 14 ? `${value.slice(0,8)}…${value.slice(-6)}` : (value || '—');
  const calcMoney = (value) => Number(value || 0).toLocaleString([], {minimumFractionDigits:2,maximumFractionDigits:2});
  const bpsMinor = (principalMinor, bps) => Math.floor(Number(principalMinor || 0) * Number(bps || 0) / 10000);
  const nextPayoutInfo = (deposits, terms) => {
    const active = (deposits || []).filter((x) => x.status === 'active');
    if (!active.length) return null;
    const sorted = active.slice().sort((a, b) => Number(a.next_payout_at || 0) - Number(b.next_payout_at || 0));
    const deposit = sorted[0];
    const totalDays = Math.max(1, Number(terms.payout_days || 20));
    const day = Math.min(totalDays, Number(deposit.scheduled_days || 0) + 1);
    const principal = Number(deposit.principal_minor || 0);
    const daily = bpsMinor(principal, terms.daily_profit_bps);
    let amount = daily;
    if (day >= totalDays) amount += principal;
    return { at: deposit.next_payout_at, amount_minor: amount, day, totalDays, includes_principal: day >= totalDays };
  };
  const projectedRemainingMinor = (deposits, terms) => {
    const totalDays = Math.max(0, Number(terms.payout_days || 0));
    const bps = Number(terms.daily_profit_bps || 0);
    let total = 0;
    (deposits || []).filter((x) => x.status === 'active').forEach((d) => {
      const principal = Number(d.principal_minor || 0);
      const scheduled = Number(d.scheduled_days || 0);
      const left = Math.max(0, totalDays - scheduled);
      total += bpsMinor(principal, bps) * left + principal;
    });
    return total;
  };
  const depositPaidMinor = (deposit, terms) => {
    const daily = bpsMinor(deposit.principal_minor, terms.daily_profit_bps);
    const paidDays = Number(deposit.paid_days || 0);
    let paid = daily * paidDays;
    const totalDays = Math.max(1, Number(terms.payout_days || 0));
    // Count principal only for a finished cycle, not for admin early-close.
    if (deposit.status === 'completed' && paidDays >= totalDays) {
      paid += Number(deposit.principal_minor || 0);
    }
    return paid;
  };
  const depositRemainingMinor = (deposit, terms) => {
    if (deposit.status !== 'active') return 0;
    const totalDays = Math.max(0, Number(terms.payout_days || 0));
    const scheduled = Number(deposit.scheduled_days || 0);
    const left = Math.max(0, totalDays - scheduled);
    const principal = Number(deposit.principal_minor || 0);
    return bpsMinor(principal, terms.daily_profit_bps) * left + principal;
  };

  const LANGS = [
    ['ru','RU','Русский','Русский'],['en','EN','English','English'],['uk','UA','Українська','Українська'],
    ['bg','BG','Български','Български'],['kk','KZ','Қазақша','Қазақша'],['be','BY','Беларуская','Беларуская'],
    ['es','ES','Español','Español'],['it','IT','Italiano','Italiano'],['tr','TR','Türkçe','Türkçe'],['tk','TM','Türkmençe','Türkmençe']
  ];

  const I18N = {
    ru: {
      sessionTitle:'Нужна авторизация Telegram',sessionText:'Для старой сессии после обновления один раз отправьте боту /start и откройте NOVERA из нового сообщения. Дальше /start повторять не нужно.',close:'Закрыть',connecting:'Подключение',dashboard:'ЛИЧНЫЙ КАБИНЕТ',welcome:'Добро пожаловать',heroSubtitle:'Ваши активы, выплаты и команда в одном месте.',activeAssets:'Сейчас в работе',totalDeposited:'Всего пополнено',totalPaid:'Получено выплат',team:'Команда',people:'участников',partnerIncome:'Партнёрский доход',quickActions:'БЫСТРЫЕ ДЕЙСТВИЯ',manageFunds:'Управление',deposit:'Пополнить',bep20:'USDT · BEP-20',assets:'Активы',activeAndCompleted:'активные и завершённые',referrals:'Рефералы',fiveLevels:'5 уровней',history:'История',allOperations:'все операции',currentTerms:'ТЕКУЩИЕ УСЛОВИЯ',minimum:'Минимум',period:'Период',dailyRate:'Ставка/день',termsFineprint:'Фактические параметры отображаются из текущей конфигурации сервиса.',portfolio:'ПОРТФЕЛЬ',assetsDesc:'Активные и завершённые депозиты с прогрессом выплат.',wallet:'Кошелёк',depositAndPayout:'Пополнение и выплаты',walletDesc:'Адрес для выплат и создание точной заявки на пополнение USDT BEP-20.',payoutWallet:'Кошелёк для выплат',payoutWalletHint:'BNB Smart Chain · адрес 0x…',address:'Адрес',save:'Сохранить',newDeposit:'Новое пополнение',amount:'Сумма USDT',createInvoice:'Создать заявку',networkWarningTitle:'Проверьте сеть и точную сумму',networkWarningText:'Отправляйте только USDT BEP-20 на показанный адрес и ровно ту сумму, которую сформировала заявка.',partnerProgram:'ПАРТНЁРСКАЯ ПРОГРАММА',teamDesc:'Реферальная ссылка, пять уровней и фактическая статистика вашей структуры.',referralLink:'Ваша реферальная ссылка',copy:'Копировать',structure:'СТРУКТУРА',members:'Участники',activity:'АКТИВНОСТЬ',historyDesc:'Депозиты и выплаты в хронологическом порядке.',all:'Все',deposits:'Депозиты',payouts:'Выплаты',account:'АККАУНТ',profile:'Профиль',support:'Поддержка',adminPanel:'Админ-панель',adminDesc:'Пользователи, операции, рассылки и состояние системы.',overview:'Обзор',users:'Пользователи',broadcasts:'Рассылка',terms:'Условия',system:'Система',logs:'Логи',userSearch:'Поиск по ID или @username',search:'Найти',failed:'Ошибки',newBroadcast:'Новая рассылка',blockedExcluded:'Заблокированные пользователи исключаются автоматически',audience:'Аудитория',allUsers:'Все пользователи',investors:'Только инвесторы',partners:'Только партнёры',message:'Сообщение',send:'Отправить',home:'Главная',admin:'Админ',language:'Язык',user:'Пользователь',online:'Онлайн',blocked:'Заблокирован',active:'Активный',completed:'Завершён',paused:'Пауза',error:'Ошибка',pending:'Ожидает',paid:'Оплачен',expired:'Истёк',confirmed:'Подтверждён',queued:'В очереди',signed:'Подписан',broadcast:'Отправлен',daily:'Выплата',referral:'Реферальная',level:'Уровень',turnover:'Оборот',earned:'Получено',waiting:'Ожидает',personal:'Лично',line:'Линия',activeCount:'Активных',completedCount:'Завершённых',principal:'Сумма',progress:'Прогресс',days:'дней',noAssets:'Активов пока нет.',noHistory:'История операций пока пуста.',noMembers:'Участников в структуре пока нет.',walletSaved:'Кошелёк сохранён',invalidWallet:'Проверьте BSC-адрес',invoiceCreated:'Заявка создана',network:'Сеть',exactAmount:'Точная сумма',validUntil:'Действует до',copyAddress:'Адрес',copyAmount:'Сумма',copyAll:'Все реквизиты',copied:'Скопировано',copyFailed:'Не удалось скопировать',sessionExpired:'Сессия Telegram устарела',openFromTelegram:'Откройте NOVERA через кнопку Mini App в Telegram.',authFailed:'Не удалось авторизоваться',role:'Роль',telegramId:'Telegram ID',registered:'Регистрация',payoutAddress:'Кошелёк выплат',referrer:'Пригласил',none:'—',adminRole:'Администратор',userRole:'Пользователь',refresh:'Обновить',newUsers:'Новых за сутки',active7d:'Активных 7 дней',activeDeposits:'Активных депозитов',failedPayouts:'Проблемных выплат',deposited:'Пополнено',paidOut:'Выплачено',today:'За сутки',netFlow:'Депозиты − подтвержд. выплаты',openDetails:'Открыть',block:'Заблокировать',unblock:'Разблокировать',transactions:'Транзакции',status:'Статус',attempts:'Попытки',retry:'Повторить',broadcastSent:'Рассылка создана',emptyMessage:'Введите сообщение',systemOnline:'Система работает',configured:'Настроено',notConfigured:'Не настроено',running:'Работает',stopped:'Остановлено',treasury:'Казна',confirmations:'Подтверждения',scanInterval:'Интервал сканирования',noLogs:'Событий пока нет.',noUsers:'Пользователи не найдены.',noDeposits:'Депозитов пока нет.',noPayouts:'Выплат пока нет.',notificationCenter:'ЦЕНТР СОБЫТИЙ',notifications:'Уведомления',notificationsDesc:'Пополнения, выплаты и события партнёрской программы.',markAllRead:'Прочитать все',partnerProgramShort:'Партнёрка',noNotifications:'Уведомлений пока нет.',newNotification:'Новое уведомление',telegramPushHint:'Сообщения бота работают как push-уведомления Telegram.'
    },
    en: {dashboard:'DASHBOARD',welcome:'Welcome',heroSubtitle:'Your assets, payouts and team in one place.',activeAssets:'Active now',totalDeposited:'Total deposited',totalPaid:'Total paid',team:'Team',people:'members',partnerIncome:'Partner income',quickActions:'QUICK ACTIONS',manageFunds:'Manage',deposit:'Deposit',assets:'Assets',referrals:'Referrals',history:'History',wallet:'Wallet',profile:'Profile',support:'Support',home:'Home',admin:'Admin',language:'Language',currentTerms:'CURRENT TERMS',minimum:'Minimum',period:'Period',dailyRate:'Rate/day',portfolio:'PORTFOLIO',assetsDesc:'Active and completed deposits with payout progress.',depositAndPayout:'Deposits & payouts',payoutWallet:'Payout wallet',address:'Address',save:'Save',newDeposit:'New deposit',amount:'USDT amount',createInvoice:'Create invoice',partnerProgram:'PARTNER PROGRAM',referralLink:'Your referral link',copy:'Copy',members:'Members',activity:'ACTIVITY',all:'All',deposits:'Deposits',payouts:'Payouts',account:'ACCOUNT',adminPanel:'Admin panel',overview:'Overview',users:'Users',broadcasts:'Broadcasts',terms:'Terms',system:'System',logs:'Logs',search:'Search',failed:'Failed',send:'Send',user:'User',online:'Online',connecting:'Connecting',sessionTitle:'Telegram authorization required',sessionText:'For an old session after this update, use /start once and open NOVERA from the new message. You will not need /start again.',close:'Close',active:'Active',completed:'Completed',pending:'Pending',confirmed:'Confirmed',queued:'Queued',error:'Error',level:'Level',turnover:'Turnover',earned:'Earned',waiting:'Pending',personal:'Personal',line:'Line',activeCount:'Active',completedCount:'Completed',principal:'Amount',progress:'Progress',days:'days',noAssets:'No assets yet.',noHistory:'No activity yet.',noMembers:'No members yet.',walletSaved:'Wallet saved',invalidWallet:'Check the BSC address',invoiceCreated:'Invoice created',network:'Network',exactAmount:'Exact amount',validUntil:'Valid until',copyAddress:'Address',copyAmount:'Amount',copyAll:'Copy details',copied:'Copied',copyFailed:'Copy failed',sessionExpired:'Telegram session expired',openFromTelegram:'Open NOVERA using the Mini App button in Telegram.',authFailed:'Authentication failed',role:'Role',telegramId:'Telegram ID',registered:'Registered',payoutAddress:'Payout wallet',referrer:'Referrer',adminRole:'Administrator',userRole:'User',refresh:'Refresh',newUsers:'New 24h',active7d:'Active 7d',activeDeposits:'Active deposits',failedPayouts:'Failed payouts',deposited:'Deposited',paidOut:'Paid',today:'24h',netFlow:'Deposits − confirmed payouts',openDetails:'Details',block:'Block',unblock:'Unblock',retry:'Retry',broadcastSent:'Broadcast created',emptyMessage:'Enter a message',systemOnline:'System online',configured:'Configured',notConfigured:'Not configured',running:'Running',stopped:'Stopped',treasury:'Treasury',confirmations:'Confirmations',scanInterval:'Scan interval',noLogs:'No events yet.',noUsers:'No users found.',noDeposits:'No deposits yet.',noPayouts:'No payouts yet.',notificationCenter:'EVENT CENTER',notifications:'Notifications',notificationsDesc:'Deposits, payouts and partner-program events.',markAllRead:'Mark all read',partnerProgramShort:'Partners',noNotifications:'No notifications yet.',newNotification:'New notification',telegramPushHint:'Bot messages work as Telegram push notifications.'},
    uk: {dashboard:'ОСОБИСТИЙ КАБІНЕТ',welcome:'Ласкаво просимо',heroSubtitle:'Ваші активи, виплати та команда в одному місці.',activeAssets:'Зараз у роботі',totalDeposited:'Всього поповнено',totalPaid:'Отримано виплат',team:'Команда',people:'учасників',partnerIncome:'Партнерський дохід',deposit:'Поповнити',assets:'Активи',referrals:'Реферали',history:'Історія',wallet:'Гаманець',profile:'Профіль',support:'Підтримка',home:'Головна',admin:'Адмін',language:'Мова',minimum:'Мінімум',period:'Період',dailyRate:'Ставка/день',depositAndPayout:'Поповнення і виплати',payoutWallet:'Гаманець для виплат',address:'Адреса',save:'Зберегти',newDeposit:'Нове поповнення',amount:'Сума USDT',createInvoice:'Створити заявку',partnerProgram:'ПАРТНЕРСЬКА ПРОГРАМА',referralLink:'Ваше реферальне посилання',copy:'Копіювати',members:'Учасники',activity:'АКТИВНІСТЬ',all:'Усі',deposits:'Депозити',payouts:'Виплати',account:'АКАУНТ',adminPanel:'Адмін-панель',users:'Користувачі',broadcasts:'Розсилка',terms:'Умови',system:'Система',logs:'Логи',search:'Знайти',send:'Надіслати',online:'Онлайн',connecting:'Підключення',sessionTitle:'Сесія Telegram застаріла',sessionText:'Закрийте Mini App і відкрийте його знову з бота.',close:'Закрити'},
    bg: {welcome:'Добре дошли',team:'Екип',deposit:'Депозит',assets:'Активи',referrals:'Реферали',history:'История',wallet:'Портфейл',profile:'Профил',support:'Поддръжка',home:'Начало',language:'Език',save:'Запази',copy:'Копирай',users:'Потребители',deposits:'Депозити',payouts:'Плащания',system:'Система',logs:'Логове',send:'Изпрати',search:'Търси'},
    kk: {welcome:'Қош келдіңіз',team:'Команда',deposit:'Толықтыру',assets:'Активтер',referrals:'Рефералдар',history:'Тарих',wallet:'Әмиян',profile:'Профиль',support:'Қолдау',home:'Басты',language:'Тіл',save:'Сақтау',copy:'Көшіру',users:'Пайдаланушылар',deposits:'Депозиттер',payouts:'Төлемдер',system:'Жүйе',logs:'Логтар',send:'Жіберу',search:'Іздеу'},
    be: {welcome:'Сардэчна запрашаем',team:'Каманда',deposit:'Папоўніць',assets:'Актывы',referrals:'Рэфералы',history:'Гісторыя',wallet:'Кашалёк',profile:'Профіль',support:'Падтрымка',home:'Галоўная',language:'Мова',save:'Захаваць',copy:'Капіяваць',users:'Карыстальнікі',deposits:'Дэпазіты',payouts:'Выплаты',system:'Сістэма',logs:'Логі',send:'Адправіць',search:'Знайсці'},
    es: {welcome:'Bienvenido',team:'Equipo',deposit:'Depositar',assets:'Activos',referrals:'Referidos',history:'Historial',wallet:'Cartera',profile:'Perfil',support:'Soporte',home:'Inicio',language:'Idioma',save:'Guardar',copy:'Copiar',users:'Usuarios',deposits:'Depósitos',payouts:'Pagos',system:'Sistema',logs:'Registros',send:'Enviar',search:'Buscar'},
    it: {welcome:'Benvenuto',team:'Squadra',deposit:'Deposita',assets:'Attività',referrals:'Referral',history:'Cronologia',wallet:'Portafoglio',profile:'Profilo',support:'Supporto',home:'Home',language:'Lingua',save:'Salva',copy:'Copia',users:'Utenti',deposits:'Depositi',payouts:'Pagamenti',system:'Sistema',logs:'Log',send:'Invia',search:'Cerca'},
    tr: {welcome:'Hoş geldiniz',team:'Ekip',deposit:'Yatır',assets:'Varlıklar',referrals:'Referanslar',history:'Geçmiş',wallet:'Cüzdan',profile:'Profil',support:'Destek',home:'Ana sayfa',language:'Dil',save:'Kaydet',copy:'Kopyala',users:'Kullanıcılar',deposits:'Yatırımlar',payouts:'Ödemeler',system:'Sistem',logs:'Kayıtlar',send:'Gönder',search:'Ara'},
    tk: {welcome:'Hoş geldiňiz',team:'Topar',deposit:'Goýum',assets:'Aktiwler',referrals:'Referallar',history:'Taryh',wallet:'Gapjyk',profile:'Profil',support:'Goldaw',home:'Baş sahypa',language:'Dil',save:'Ýatda sakla',copy:'Göçür',users:'Ulanyjylar',deposits:'Goýumlar',payouts:'Tölegler',system:'Ulgam',logs:'Loglar',send:'Iber',search:'Gözle'}
  };

  const NOTICE_I18N = {
    ru:{administrators:'Администраторы',adminManagement:'Управление администраторами',adminManagementHint:'Полный доступ к админ-панели и команде /admin.',adminIdentifier:'Telegram ID или @username',addAdmin:'Добавить',removeAdmin:'Убрать права',adminUserMustExist:'Пользователь должен хотя бы один раз открыть NOVERA, чтобы появиться в базе.',protectedAdmin:'Основной администратор',fullAdmin:'Полные права',adminAdded:'Администратор добавлен',adminRemoved:'Права администратора удалены',userNotFound:'Пользователь не найден',invalidAdmin:'Проверьте Telegram ID или @username',cannotRemoveSelf:'Нельзя снять права администратора у самого себя',cannotRemoveOwner:'Основного администратора нельзя удалить',adminGrantNotFound:'Права администратора уже отсутствуют',accountBlocked:'Аккаунт заблокирован',adminAccessRequired:'Недостаточно прав администратора',tooManyRequests:'Слишком много запросов. Попробуйте немного позже.',requestTooLarge:'Слишком большой запрос',invalidData:'Проверьте введённые данные',depositsDisabled:'Пополнения временно недоступны',treasuryNotConfigured:'Кошелёк системы не настроен',requestFailed:'Не удалось выполнить запрос. Попробуйте ещё раз.',loginLinkExpired:'Ссылка входа устарела. Отправьте /start и откройте новую кнопку.',blockedNow:'Пользователь заблокирован',unblockedNow:'Пользователь разблокирован',payoutQueued:'Выплата поставлена в очередь',maximum:'Максимум',uptime:'Время работы',workers:'Фоновые процессы',signing:'Подпись транзакций',source:'Источник',addedBy:'Добавил',remove:'Удалить',bootstrapSource:'Основной',dynamicSource:'Добавлен',noAdmins:'Дополнительных администраторов пока нет.'},
    en:{administrators:'Administrators',adminManagement:'Administrator management',adminManagementHint:'Full access to the admin panel and /admin command.',adminIdentifier:'Telegram ID or @username',addAdmin:'Add',removeAdmin:'Remove access',adminUserMustExist:'The user must open NOVERA at least once before they can be promoted.',protectedAdmin:'Primary administrator',fullAdmin:'Full access',adminAdded:'Administrator added',adminRemoved:'Administrator access removed',userNotFound:'User not found',invalidAdmin:'Check the Telegram ID or @username',cannotRemoveSelf:'You cannot remove your own administrator access',cannotRemoveOwner:'The primary administrator cannot be removed',adminGrantNotFound:'Administrator access is already absent',accountBlocked:'Account is blocked',adminAccessRequired:'Administrator access is required',tooManyRequests:'Too many requests. Please try again shortly.',requestTooLarge:'The request is too large',invalidData:'Check the entered data',depositsDisabled:'Deposits are temporarily unavailable',treasuryNotConfigured:'System wallet is not configured',requestFailed:'Request failed. Please try again.',loginLinkExpired:'The login link has expired. Send /start and use the new button.',blockedNow:'User blocked',unblockedNow:'User unblocked',payoutQueued:'Payout queued',maximum:'Maximum',uptime:'Uptime',workers:'Workers',signing:'Transaction signing',source:'Source',addedBy:'Added by',remove:'Remove',bootstrapSource:'Primary',dynamicSource:'Added',noAdmins:'No additional administrators yet.'},
    uk:{administrators:'Адміністратори',adminManagement:'Керування адміністраторами',adminManagementHint:'Повний доступ до адмін-панелі та команди /admin.',adminIdentifier:'Telegram ID або @username',addAdmin:'Додати',removeAdmin:'Зняти права',adminUserMustExist:'Користувач має хоча б один раз відкрити NOVERA.',protectedAdmin:'Основний адміністратор',fullAdmin:'Повні права',adminAdded:'Адміністратора додано',adminRemoved:'Права адміністратора видалено',userNotFound:'Користувача не знайдено',invalidAdmin:'Перевірте Telegram ID або @username',cannotRemoveSelf:'Не можна зняти права адміністратора у себе',cannotRemoveOwner:'Основного адміністратора не можна видалити',adminGrantNotFound:'Права адміністратора вже відсутні',accountBlocked:'Акаунт заблоковано',adminAccessRequired:'Потрібні права адміністратора',tooManyRequests:'Забагато запитів. Спробуйте трохи пізніше.',requestTooLarge:'Запит завеликий',invalidData:'Перевірте введені дані',depositsDisabled:'Поповнення тимчасово недоступні',treasuryNotConfigured:'Системний гаманець не налаштовано',requestFailed:'Не вдалося виконати запит. Спробуйте ще раз.',loginLinkExpired:'Посилання входу застаріло. Надішліть /start і відкрийте нову кнопку.',blockedNow:'Користувача заблоковано',unblockedNow:'Користувача розблоковано',payoutQueued:'Виплату поставлено в чергу',maximum:'Максимум',uptime:'Час роботи',workers:'Фонові процеси',signing:'Підпис транзакцій',source:'Джерело',addedBy:'Додав',remove:'Видалити',bootstrapSource:'Основний',dynamicSource:'Доданий',noAdmins:'Додаткових адміністраторів поки немає.'},
    bg:{sessionTitle:'Сесията на Telegram е изтекла',sessionText:'Затворете Mini App и го отворете отново от бота.',close:'Затвори',sessionExpired:'Сесията на Telegram е изтекла',openFromTelegram:'Отворете NOVERA чрез бутона Mini App в Telegram.',authFailed:'Неуспешно удостоверяване',walletSaved:'Портфейлът е запазен',invalidWallet:'Проверете BSC адреса',invoiceCreated:'Заявката е създадена',copied:'Копирано',copyFailed:'Неуспешно копиране',emptyMessage:'Въведете съобщение',broadcastSent:'Разпращането е създадено',payoutQueued:'Плащането е поставено на опашка',blockedNow:'Потребителят е блокиран',unblockedNow:'Потребителят е отблокиран',adminAdded:'Администраторът е добавен',adminRemoved:'Администраторските права са премахнати',userNotFound:'Потребителят не е намерен',requestFailed:'Заявката не бе изпълнена. Опитайте отново.',tooManyRequests:'Твърде много заявки. Опитайте малко по-късно.',accountBlocked:'Акаунтът е блокиран',administrators:'Администратори',addAdmin:'Добави',removeAdmin:'Премахни права'},
    kk:{sessionTitle:'Telegram сессиясының мерзімі аяқталды',sessionText:'Mini App-ты жауып, боттан қайта ашыңыз.',close:'Жабу',sessionExpired:'Telegram сессиясының мерзімі аяқталды',openFromTelegram:'NOVERA-ты Telegram-дағы Mini App батырмасы арқылы ашыңыз.',authFailed:'Авторизация сәтсіз аяқталды',walletSaved:'Әмиян сақталды',invalidWallet:'BSC мекенжайын тексеріңіз',invoiceCreated:'Өтінім жасалды',copied:'Көшірілді',copyFailed:'Көшіру мүмкін болмады',emptyMessage:'Хабарлама енгізіңіз',broadcastSent:'Тарату жасалды',payoutQueued:'Төлем кезекке қойылды',blockedNow:'Пайдаланушы бұғатталды',unblockedNow:'Пайдаланушы бұғаттан шығарылды',adminAdded:'Әкімші қосылды',adminRemoved:'Әкімші құқықтары алынды',userNotFound:'Пайдаланушы табылмады',requestFailed:'Сұрауды орындау мүмкін болмады. Қайта көріңіз.',tooManyRequests:'Сұраулар тым көп. Сәл кейінірек қайталап көріңіз.',accountBlocked:'Аккаунт бұғатталған',administrators:'Әкімшілер',addAdmin:'Қосу',removeAdmin:'Құқықты алып тастау'},
    be:{sessionTitle:'Сесія Telegram скончылася',sessionText:'Закрыйце Mini App і адкрыйце яго зноў з бота.',close:'Закрыць',sessionExpired:'Сесія Telegram скончылася',openFromTelegram:'Адкрыйце NOVERA праз кнопку Mini App у Telegram.',authFailed:'Не ўдалося аўтарызавацца',walletSaved:'Кашалёк захаваны',invalidWallet:'Праверце BSC-адрас',invoiceCreated:'Заяўка створана',copied:'Скапіравана',copyFailed:'Не ўдалося скапіяваць',emptyMessage:'Увядзіце паведамленне',broadcastSent:'Рассылка створана',payoutQueued:'Выплата пастаўлена ў чаргу',blockedNow:'Карыстальнік заблакаваны',unblockedNow:'Карыстальнік разблакаваны',adminAdded:'Адміністратар дададзены',adminRemoved:'Правы адміністратара выдалены',userNotFound:'Карыстальнік не знойдзены',requestFailed:'Не ўдалося выканаць запыт. Паспрабуйце яшчэ раз.',tooManyRequests:'Занадта шмат запытаў. Паспрабуйце пазней.',accountBlocked:'Акаўнт заблакаваны',administrators:'Адміністратары',addAdmin:'Дадаць',removeAdmin:'Зняць правы'},
    es:{sessionTitle:'La sesión de Telegram ha caducado',sessionText:'Cierra la Mini App y vuelve a abrirla desde el bot.',close:'Cerrar',sessionExpired:'La sesión de Telegram ha caducado',openFromTelegram:'Abre NOVERA con el botón Mini App de Telegram.',authFailed:'No se pudo autenticar',walletSaved:'Cartera guardada',invalidWallet:'Comprueba la dirección BSC',invoiceCreated:'Solicitud creada',copied:'Copiado',copyFailed:'No se pudo copiar',emptyMessage:'Introduce un mensaje',broadcastSent:'Difusión creada',payoutQueued:'Pago puesto en cola',blockedNow:'Usuario bloqueado',unblockedNow:'Usuario desbloqueado',adminAdded:'Administrador añadido',adminRemoved:'Acceso de administrador eliminado',userNotFound:'Usuario no encontrado',requestFailed:'No se pudo completar la solicitud. Inténtalo de nuevo.',tooManyRequests:'Demasiadas solicitudes. Inténtalo de nuevo en breve.',accountBlocked:'La cuenta está bloqueada',administrators:'Administradores',addAdmin:'Añadir',removeAdmin:'Quitar acceso'},
    it:{sessionTitle:'La sessione Telegram è scaduta',sessionText:'Chiudi la Mini App e riaprila dal bot.',close:'Chiudi',sessionExpired:'La sessione Telegram è scaduta',openFromTelegram:'Apri NOVERA con il pulsante Mini App in Telegram.',authFailed:'Autenticazione non riuscita',walletSaved:'Portafoglio salvato',invalidWallet:'Controlla l’indirizzo BSC',invoiceCreated:'Richiesta creata',copied:'Copiato',copyFailed:'Impossibile copiare',emptyMessage:'Inserisci un messaggio',broadcastSent:'Invio creato',payoutQueued:'Pagamento messo in coda',blockedNow:'Utente bloccato',unblockedNow:'Utente sbloccato',adminAdded:'Amministratore aggiunto',adminRemoved:'Accesso amministratore rimosso',userNotFound:'Utente non trovato',requestFailed:'Impossibile completare la richiesta. Riprova.',tooManyRequests:'Troppe richieste. Riprova tra poco.',accountBlocked:'Account bloccato',administrators:'Amministratori',addAdmin:'Aggiungi',removeAdmin:'Rimuovi accesso'},
    tr:{sessionTitle:'Telegram oturumu sona erdi',sessionText:'Mini App’i kapatın ve bottan tekrar açın.',close:'Kapat',sessionExpired:'Telegram oturumu sona erdi',openFromTelegram:'NOVERA’u Telegram’daki Mini App düğmesinden açın.',authFailed:'Kimlik doğrulama başarısız',walletSaved:'Cüzdan kaydedildi',invalidWallet:'BSC adresini kontrol edin',invoiceCreated:'Talep oluşturuldu',copied:'Kopyalandı',copyFailed:'Kopyalanamadı',emptyMessage:'Bir mesaj girin',broadcastSent:'Yayın oluşturuldu',payoutQueued:'Ödeme kuyruğa alındı',blockedNow:'Kullanıcı engellendi',unblockedNow:'Kullanıcının engeli kaldırıldı',adminAdded:'Yönetici eklendi',adminRemoved:'Yönetici yetkisi kaldırıldı',userNotFound:'Kullanıcı bulunamadı',requestFailed:'İstek tamamlanamadı. Tekrar deneyin.',tooManyRequests:'Çok fazla istek. Kısa süre sonra tekrar deneyin.',accountBlocked:'Hesap engellendi',administrators:'Yöneticiler',addAdmin:'Ekle',removeAdmin:'Yetkiyi kaldır'},
    tk:{sessionTitle:'Telegram sessiýasynyň möhleti gutardy',sessionText:'Mini App-y ýapyň we botdan täzeden açyň.',close:'Ýap',sessionExpired:'Telegram sessiýasynyň möhleti gutardy',openFromTelegram:'NOVERA-y Telegram-daky Mini App düwmesi arkaly açyň.',authFailed:'Tassyklama başartmady',walletSaved:'Gapjyk ýatda saklandy',invalidWallet:'BSC salgysyny barlaň',invoiceCreated:'Arza döredildi',copied:'Göçürildi',copyFailed:'Göçürip bolmady',emptyMessage:'Habar giriziň',broadcastSent:'Ugratma döredildi',payoutQueued:'Töleg nobata goýuldy',blockedNow:'Ulanyjy petiklendi',unblockedNow:'Ulanyjy açyldy',adminAdded:'Administrator goşuldy',adminRemoved:'Administrator hukuklary aýryldy',userNotFound:'Ulanyjy tapylmady',requestFailed:'Talaby ýerine ýetirip bolmady. Gaýtadan synanyşyň.',tooManyRequests:'Talaplar örän köp. Biraz soň gaýtadan synanyşyň.',accountBlocked:'Hasap petiklenen',administrators:'Administratorlar',addAdmin:'Goş',removeAdmin:'Hukugy aýyr'}
  };
  Object.entries(NOTICE_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const CONTROL_I18N = {
    ru:{accountBalance:'Баланс аккаунта',internalBalance:'Внутренний баланс',balanceReason:'Причина изменения',balanceReasonHint:'Причина обязательна и сохраняется в журнале действий.',setBalance:'Изменить баланс',balanceSaved:'Баланс пользователя изменён',walletUpdated:'Кошелёк пользователя изменён',walletManagement:'Кошелёк выплат',walletManagementHint:'Можно заменить или очистить адрес выплат пользователя.',clearWallet:'Очистить',balanceHistory:'История изменений баланса',noBalanceHistory:'Изменений баланса пока нет.',formatHint:'Выделите текст и примените форматирование. В Telegram отправляется безопасный HTML.',attachImage:'Прикрепить картинку',imageTooLarge:'Картинка должна быть не больше 5 МБ',imageType:'Поддерживаются только JPEG и PNG',broadcastButtons:'Кнопки',broadcastButtonsHint:'До 8 кнопок-ссылок под сообщением.',addButton:'+ Кнопка',buttonText:'Текст кнопки',buttonUrl:'Ссылка https://…',linkUrl:'Введите ссылку для выделенного текста',broadcastMediaFailed:'Не удалось загрузить картинку',broadcastRequiresContent:'Добавьте текст или картинку',settingsTitle:'Параметры проекта',settingsHint:'Изменения сохраняются в базе и применяются без переустановки.',saveSettings:'Сохранить параметры',settingsSaved:'Параметры сохранены',profitSettings:'Доходность и депозиты',operationsSettings:'Операционные настройки',referralSettings:'Партнёрские уровни',dailyRatePercent:'Ставка в день, %',payoutDays:'Количество дней выплат',depositMin:'Минимальный депозит, USDT',depositMax:'Максимальный депозит, USDT',invoiceTtl:'Срок заявки, минут',acceptDeposits:'Принимать новые депозиты',enablePayouts:'Разрешить выплаты',confirmationBlocksLabel:'Подтверждений блока',scanIntervalSeconds:'Интервал сканирования, сек.',supportUrl:'Ссылка поддержки',levelRate:'Ставка уровня, %',personalThreshold:'Личный депозит, USDT',lineThreshold:'Оборот линии, USDT',settingsPayoutDaysConflict:'Нельзя установить период ниже уже пройденного дня активного депозита.',invalidButton:'Проверьте текст и ссылку кнопки',imageAttached:'Картинка прикреплена',removeImage:'Убрать картинку',manualBalanceNote:'Это внутренний учётный баланс NOVERA. Он хранится отдельно от on-chain депозитов и казны.',chainConfigTitle:'Blockchain и боевой режим',chainConfigHint:'RPC, WSS и seed-фраза не отображаются. Пустое поле сохраняет текущее значение.',chainMode:'Режим сети',modeProduction:'BSC Mainnet · боевой',modeTestnet:'BSC Testnet',modeOff:'Blockchain выключен',tokenContract:'Контракт токена',scanStartBlock:'Стартовый блок сканирования',treasuryDerived:'Кошелёк казны',rpcEndpoint:'Новый HTTPS RPC',wssEndpoint:'Новый приватный WSS',seedPhraseWriteOnly:'Новая seed-фраза',secretKeepHint:'Оставьте пустым, чтобы сохранить текущий секрет.',rpcCurrent:'Текущий RPC',wssCurrent:'Текущий WSS',seedCurrent:'Seed-фраза',secretConfigured:'настроена',secretMissing:'не настроена',saveRestart:'Сохранить и перезапустить',chainConfigSaved:'Blockchain-параметры сохранены. NOVERA перезапускается…',chainHealthFailed:'Новые RPC/WSS не прошли проверку сети',seedInvalid:'Проверьте seed-фразу',invalidContract:'Проверьте адрес контракта токена',restartHint:'После сохранения контейнер автоматически перезапустится; повторная установка не нужна.',writeOnly:'только запись'},
    en:{accountBalance:'Account balance',internalBalance:'Internal balance',balanceReason:'Change reason',balanceReasonHint:'A reason is required and saved to the audit log.',setBalance:'Set balance',balanceSaved:'User balance updated',walletUpdated:'User wallet updated',walletManagement:'Payout wallet',walletManagementHint:'Replace or clear the user payout address.',clearWallet:'Clear',balanceHistory:'Balance change history',noBalanceHistory:'No balance changes yet.',formatHint:'Select text and apply formatting. Safe HTML is sent to Telegram.',attachImage:'Attach image',imageTooLarge:'Image must be 5 MB or smaller',imageType:'Only JPEG and PNG are supported',broadcastButtons:'Buttons',broadcastButtonsHint:'Up to 8 URL buttons under the message.',addButton:'+ Button',buttonText:'Button text',buttonUrl:'Link https://…',linkUrl:'Enter a link for the selected text',broadcastMediaFailed:'Could not upload image',broadcastRequiresContent:'Add text or an image',settingsTitle:'Project parameters',settingsHint:'Changes are saved in the database and applied without reinstalling.',saveSettings:'Save parameters',settingsSaved:'Parameters saved',profitSettings:'Yield and deposits',operationsSettings:'Operational settings',referralSettings:'Referral levels',dailyRatePercent:'Daily rate, %',payoutDays:'Payout days',depositMin:'Minimum deposit, USDT',depositMax:'Maximum deposit, USDT',invoiceTtl:'Invoice TTL, minutes',acceptDeposits:'Accept new deposits',enablePayouts:'Enable payouts',confirmationBlocksLabel:'Confirmation blocks',scanIntervalSeconds:'Scan interval, sec.',supportUrl:'Support URL',levelRate:'Level rate, %',personalThreshold:'Personal deposit, USDT',lineThreshold:'Line turnover, USDT',settingsPayoutDaysConflict:'Payout days cannot be below progress already reached by an active deposit.',invalidButton:'Check the button text and URL',imageAttached:'Image attached',removeImage:'Remove image',manualBalanceNote:'This is the internal NOVERA account balance. It is stored separately from on-chain deposits and treasury.',chainConfigTitle:'Blockchain and live mode',chainConfigHint:'RPC, WSS and seed phrase are never displayed. Leave a field blank to keep its current value.',chainMode:'Network mode',modeProduction:'BSC Mainnet · live',modeTestnet:'BSC Testnet',modeOff:'Blockchain disabled',tokenContract:'Token contract',scanStartBlock:'Scan start block',treasuryDerived:'Treasury wallet',rpcEndpoint:'New HTTPS RPC',wssEndpoint:'New private WSS',seedPhraseWriteOnly:'New seed phrase',secretKeepHint:'Leave blank to keep the current secret.',rpcCurrent:'Current RPC',wssCurrent:'Current WSS',seedCurrent:'Seed phrase',secretConfigured:'configured',secretMissing:'not configured',saveRestart:'Save and restart',chainConfigSaved:'Blockchain settings saved. NOVERA is restarting…',chainHealthFailed:'The new RPC/WSS endpoints failed network validation',seedInvalid:'Check the seed phrase',invalidContract:'Check the token contract address',restartHint:'The container restarts automatically after saving; reinstall is not required.',writeOnly:'write only'}
  };
  Object.entries(CONTROL_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const SETUP_I18N = {
    ru:{
      ownerRequired:'Только владелец может изменить эту настройку',
      setupState:'Состояние запуска',
      setupBootstrap:'Ожидает настройки',
      setupConfigured:'Проверено, ожидает активации',
      setupActive:'Blockchain активирован',
      setupDegraded:'Blockchain заблокирован из-за ошибки',
      financialLocked:'Финансовые операции заблокированы до активации владельцем',
      investmentsEnabled:'Разрешить ручные инвестиции',
      referralsEnabled:'Разрешить партнёрские начисления',
      chainValidate:'Проверить конфигурацию',
      chainValidateHint:'RPC, WSS, контракт и signer будут проверены без включения финансовых операций.',
      chainReason:'Причина настройки',
      chainReasonPlaceholder:'Первичная настройка blockchain',
      seedWebviewWarning:'Seed будет передана через Telegram WebView. Продолжайте только на доверенном устройстве; NOVERA не покажет её повторно.',
      acceptSeedRisk:'Я понимаю риск и нахожусь на доверенном устройстве',
      chainValidated:'Конфигурация проверена. Сверьте адрес казны.',
      treasuryConfirm:'Введите полученный адрес казны полностью',
      activateChain:'Активировать blockchain',
      activationWarning:'Активация перезапустит backend. Депозиты и выплаты останутся выключенными, пока владелец не включит их в разделе «Условия».',
      chainActivationReason:'Причина активации',
      chainActivated:'Blockchain активирован; backend перезапускается',
      reopenForFreshAuth:'Для активации закройте Mini App и откройте её снова из бота',
      secretFieldsRequired:'Заполните RPC, WSS и seed phrase',
      scanBlockRequired:'Для production укажите scan start block больше 0 (блок начала сканирования депозитов)',
      treasuryConfirmMismatch:'Адрес казны введён неверно — скопируйте показанный адрес полностью',
      chainHealthFailed:'RPC/WSS не прошли проверку с VPS. Проверьте URL и доступность провайдера',
      chainDnsFailed:'DNS провайдера RPC/WSS не резолвится с VPS',
      chainPendingLost:'Сначала снова нажмите «Проверить конфигурацию» — карточка активации пропала после перезагрузки',
      scanStartHint:'Для production обязательно > 0. Пример: текущий блок BSC минус небольшой запас.',
      setupFingerprint:'Отпечаток конфигурации',
      activationStepsTitle:'Шаги запуска',
      activationStep1:'1. Проверить RPC / WSS / seed',
      activationStep2:'2. Сверить и подтвердить адрес казны',
      activationStep3:'3. Активировать blockchain',
      activationStep4:'4. Включить нужные переключатели в «Условиях»',
      postActivateChecklist:'После активации',
      postActivateTerms:'Откройте «Условия» и включите только согласованные операции (депозиты / выплаты / инвестиции / партнёрка).',
      postActivateBackup:'Сделайте off-server копию runtime_config_key.txt до первой смены конфигурации.',
      keyBackupHint:'Храните runtime_config_key.txt вне VPS. Без него encrypted chain bundle не восстановить.'
    },
    en:{
      ownerRequired:'Only the owner can change this setting',
      setupState:'Setup state',
      setupBootstrap:'Waiting for setup',
      setupConfigured:'Validated, waiting for activation',
      setupActive:'Blockchain active',
      setupDegraded:'Blockchain locked after an error',
      financialLocked:'Financial operations are locked until owner activation',
      investmentsEnabled:'Allow manual investments',
      referralsEnabled:'Allow referral accruals',
      chainValidate:'Validate configuration',
      chainValidateHint:'RPC, WSS, contract and signer are checked without enabling financial operations.',
      chainReason:'Configuration reason',
      chainReasonPlaceholder:'Initial blockchain setup',
      seedWebviewWarning:'The seed will pass through Telegram WebView. Continue only on a trusted device; NOVERA will never display it again.',
      acceptSeedRisk:'I understand the risk and use a trusted device',
      chainValidated:'Configuration validated. Verify the treasury address.',
      treasuryConfirm:'Type the derived treasury address in full',
      activateChain:'Activate blockchain',
      activationWarning:'Activation restarts the backend. Deposits and payouts remain off until the owner enables them under Terms.',
      chainActivationReason:'Activation reason',
      chainActivated:'Blockchain activated; backend is restarting',
      reopenForFreshAuth:'Close and reopen the Mini App from the bot before activation',
      secretFieldsRequired:'Enter RPC, WSS and seed phrase',
      scanBlockRequired:'Production requires a scan start block greater than 0',
      treasuryConfirmMismatch:'Treasury confirmation does not match — paste the shown address in full',
      chainHealthFailed:'RPC/WSS health check failed from the VPS. Check the provider URLs',
      chainDnsFailed:'RPC/WSS provider DNS lookup failed from the VPS',
      chainPendingLost:'Run Validate again — the activation card was lost after reload',
      scanStartHint:'Production requires > 0. Example: current BSC block minus a small margin.',
      setupFingerprint:'Configuration fingerprint',
      activationStepsTitle:'Activation steps',
      activationStep1:'1. Validate RPC / WSS / seed',
      activationStep2:'2. Confirm the treasury address',
      activationStep3:'3. Activate blockchain',
      activationStep4:'4. Enable approved switches under Terms',
      postActivateChecklist:'After activation',
      postActivateTerms:'Open Terms and enable only approved operations (deposits / payouts / investments / referrals).',
      postActivateBackup:'Keep an off-server copy of runtime_config_key.txt before any later config rotation.',
      keyBackupHint:'Store runtime_config_key.txt off the VPS. Without it the encrypted chain bundle cannot be recovered.'
    }
  };
  Object.entries(SETUP_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const STAGE_UX_I18N = {
    ru:{
      historyDesc:'Депозиты и выплаты. У каждой операции понятный статус и подсказка, нужно ли что-то делать.',
      historyNeedsAction:'Нужно действие',
      historyNoAction:'Ожидание системы',
      historyDone:'Завершено',
      historyHintFailed:'Операция не прошла. Если сумма не пришла — напишите в поддержку и укажите номер операции.',
      historyHintQueued:'В очереди на отправку. Ничего делать не нужно.',
      historyHintSigned:'Подписана, ожидает сеть. Ничего делать не нужно.',
      historyHintBroadcast:'Отправлена в сеть, ждём подтверждение.',
      historyHintExpired:'Срок заявки истёк. Создайте новую заявку на пополнение.',
      historyHintActive:'Инвестиция активна, выплаты идут по графику.',
      historyHintPaused:'Инвестиция на паузе. Обратитесь в поддержку, если это неожиданно.',
      historyHintCompleted:'Операция завершена.',
      historyHintConfirmed:'Выплата подтверждена в сети.',
      historyHintPending:'Ожидает обработки.',
      historyHintDefault:'Статус обновляется автоматически.',
      statusActive:'Активна',statusCompleted:'Завершена',statusPaused:'На паузе',statusFailed:'Ошибка',
      statusPending:'Ожидание',statusPaid:'Выплачено',statusExpired:'Истекла',statusConfirmed:'Подтверждена',
      statusQueued:'В очереди',statusSigned:'Подписана',statusBroadcast:'В сети',statusSending:'Отправка',
      levelSourceAuto:'Источник: автоматическая квалификация',
      levelSourceManual:'Источник: ручной доступ от администратора (только будущие начисления)',
      availableVsPending:'Доступно — можно вывести сейчас. В обработке — уже в очереди выплат и недоступно повторно.',
      referralFailedLabel:'Неуспешные выводы',
      withdrawDisabledPayouts:'Выводы временно отключены администратором.',
      withdrawDisabledMinimum:'Недостаточно средств: минимум {min} USDT.',
      withdrawDisabledWallet:'Сначала сохраните кошелёк выплат в профиле.',
      withdrawDisabledBootstrap:'Финансовые операции ещё не активированы владельцем.',
      noNotifications:'Пока нет уведомлений в этой категории.',
      notificationsLoadError:'Не удалось загрузить уведомления. Потяните экран или откройте раздел снова.',
      notificationCatAll:'Все',notificationCatDeposit:'Пополнения',notificationCatPayout:'Выплаты',notificationCatPartner:'Партнёрка',notificationCatSystem:'Система',
      sessionRecoverCta:'Открыть бота и нажать /start',
      sessionRecoverHint:'Если сессия устарела: закройте Mini App → отправьте боту /start → откройте NOVERA из нового сообщения.',
      unreadNotifications:'Непрочитанные',
      adminOpsHealth:'Операционное состояние',
      adminLastRefresh:'Обновлено',
      adminStuckQueue:'Застрявшие выплаты',
      adminQueuePending:'В очереди / в полёте',
      adminSafetyStatus:'Safety',
      adminCircuitOpen:'Circuit open',
      adminCircuitOk:'Circuit closed',
      adminNoStuck:'Застреваний нет',
      adminAgeSeconds:'возраст {sec} с',
      adminAgeMinutes:'возраст {min} мин',
      adminAgeHours:'возраст {hours} ч',
      adminAgeHoursMinutes:'возраст {hours} ч {min} мин',
      adminSafetyUnknown:'неизвестно',
      adminSafetyUnknownHint:'Не удалось загрузить safety — статус не подтверждён',
      adminRetryHint:'Retry безопасен только для статуса failed: операция вернётся в очередь без повторной подписи confirmed-транзакции.',
      adminDepositAge:'возраст',
      adminUsersFilterAll:'Все',
      adminUsersFilterInvestors:'С депозитами',
      adminUsersFilterBlocked:'Заблокированные',
      adminUsersShown:'Показано {shown} из {total}',
      adminUsersEmptyFilter:'Нет пользователей в этом фильтре'
    },
    en:{
      historyDesc:'Deposits and payouts with a clear status and whether you need to act.',
      historyNeedsAction:'Action needed',
      historyNoAction:'Waiting on the system',
      historyDone:'Done',
      historyHintFailed:'The operation failed. If funds did not arrive, contact support with the operation id.',
      historyHintQueued:'Queued for sending. No action needed.',
      historyHintSigned:'Signed and waiting for the network. No action needed.',
      historyHintBroadcast:'Broadcast to the network; waiting for confirmation.',
      historyHintExpired:'The invoice expired. Create a new deposit request.',
      historyHintActive:'Investment is active; payouts follow the schedule.',
      historyHintPaused:'Investment is paused. Contact support if unexpected.',
      historyHintCompleted:'Operation completed.',
      historyHintConfirmed:'Payout confirmed on-chain.',
      historyHintPending:'Waiting for processing.',
      historyHintDefault:'Status updates automatically.',
      statusActive:'Active',statusCompleted:'Completed',statusPaused:'Paused',statusFailed:'Failed',
      statusPending:'Pending',statusPaid:'Paid',statusExpired:'Expired',statusConfirmed:'Confirmed',
      statusQueued:'Queued',statusSigned:'Signed',statusBroadcast:'Broadcast',statusSending:'Sending',
      levelSourceAuto:'Source: automatic qualification',
      levelSourceManual:'Source: manual admin access (future accruals only)',
      availableVsPending:'Available can be withdrawn now. Processing is already in the payout queue and cannot be withdrawn again.',
      referralFailedLabel:'Failed withdrawals',
      withdrawDisabledPayouts:'Withdrawals are temporarily disabled by an administrator.',
      withdrawDisabledMinimum:'Insufficient funds: minimum is {min} USDT.',
      withdrawDisabledWallet:'Save a payout wallet in your profile first.',
      withdrawDisabledBootstrap:'Financial operations are not activated by the owner yet.',
      noNotifications:'No notifications in this category yet.',
      notificationsLoadError:'Could not load notifications. Reopen this screen.',
      notificationCatAll:'All',notificationCatDeposit:'Deposits',notificationCatPayout:'Payouts',notificationCatPartner:'Partners',notificationCatSystem:'System',
      sessionRecoverCta:'Open the bot and tap /start',
      sessionRecoverHint:'If the session expired: close Mini App → send /start to the bot → open NOVERA from the new message.',
      unreadNotifications:'Unread',
      adminOpsHealth:'Operations health',
      adminLastRefresh:'Refreshed',
      adminStuckQueue:'Stuck payouts',
      adminQueuePending:'Queued / in flight',
      adminSafetyStatus:'Safety',
      adminCircuitOpen:'Circuit open',
      adminCircuitOk:'Circuit closed',
      adminNoStuck:'Nothing stuck',
      adminAgeSeconds:'age {sec}s',
      adminAgeMinutes:'age {min} min',
      adminAgeHours:'age {hours} h',
      adminAgeHoursMinutes:'age {hours} h {min} min',
      adminSafetyUnknown:'unknown',
      adminSafetyUnknownHint:'Safety data unavailable — status not confirmed',
      adminRetryHint:'Retry is safe only for failed: it re-queues without re-signing a confirmed transaction.',
      adminDepositAge:'age',
      adminUsersFilterAll:'All',
      adminUsersFilterInvestors:'With deposits',
      adminUsersFilterBlocked:'Blocked',
      adminUsersShown:'Showing {shown} of {total}',
      adminUsersEmptyFilter:'No users in this filter'
    }
  };
  Object.entries(STAGE_UX_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const MASTER_FOLLOWUP_I18N = {
    ru:{
      ownerModelTitle:'Модель владельца',
      ownerModelHint:'Только immutable Owner может добавлять и снимать администраторов. Bootstrap Owner нельзя удалить.',
      ownerOnlyGrant:'Добавление администраторов доступно только владельцу.',
      protectedOwnerBadge:'Immutable Owner',
      confirmRemoveAdmin:'Снять полные права администратора у ID {id}?',
      linksAuditHint:'Ссылки сохраняются в runtime settings и попадают в журнал аудита при изменении.',
      linksPreviewHint:'Так кнопки выглядят в профиле пользователя.',
      offlineTitle:'Нет сети',
      offlineText:'Проверьте подключение. Данные обновятся автоматически, когда связь восстановится.',
      slowNetwork:'Ответ сервера занимает больше обычного…',
      requestTimeout:'Сервер не ответил вовремя. Попробуйте ещё раз.',
      networkError:'Нет ответа от сервера. Проверьте интернет и откройте Mini App снова.',
      retryConnection:'Повторить'
    },
    en:{
      ownerModelTitle:'Owner model',
      ownerModelHint:'Only the immutable Owner can grant or revoke administrators. The bootstrap Owner cannot be removed.',
      ownerOnlyGrant:'Only the owner can add administrators.',
      protectedOwnerBadge:'Immutable Owner',
      confirmRemoveAdmin:'Remove full administrator access from ID {id}?',
      linksAuditHint:'Links are stored in runtime settings and recorded in the audit log when changed.',
      linksPreviewHint:'This is how the buttons appear in the user profile.',
      offlineTitle:'You are offline',
      offlineText:'Check your connection. Data will refresh automatically when you are back online.',
      slowNetwork:'The server is taking longer than usual…',
      requestTimeout:'The server did not respond in time. Please try again.',
      networkError:'No response from the server. Check your internet and reopen Mini App.',
      retryConnection:'Retry'
    }
  };
  Object.entries(MASTER_FOLLOWUP_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const V5_I18N = {
    ru:{inviter:'Пригласитель',chat:'Чат',chatUrl:'Ссылка на чат',principalReturn:'Возврат депозита'},
    en:{inviter:'Inviter',chat:'Chat',chatUrl:'Chat URL',principalReturn:'Principal return'},
    uk:{inviter:'Запросив',chat:'Чат',chatUrl:'Посилання на чат',principalReturn:'Повернення депозиту'},
    bg:{inviter:'Поканил',chat:'Чат',chatUrl:'Линк към чата',principalReturn:'Връщане на депозита'},
    kk:{inviter:'Шақырған',chat:'Чат',chatUrl:'Чат сілтемесі',principalReturn:'Депозитті қайтару'},
    be:{inviter:'Запрасіў',chat:'Чат',chatUrl:'Спасылка на чат',principalReturn:'Вяртанне дэпазіту'},
    es:{inviter:'Invitador',chat:'Chat',chatUrl:'Enlace del chat',principalReturn:'Devolución del depósito'},
    it:{inviter:'Invitante',chat:'Chat',chatUrl:'Link della chat',principalReturn:'Restituzione deposito'},
    tr:{inviter:'Davet eden',chat:'Sohbet',chatUrl:'Sohbet bağlantısı',principalReturn:'Ana para iadesi'},
    tk:{inviter:'Çakylykçy',chat:'Çat',chatUrl:'Çat salgysy',principalReturn:'Depoziti gaýtarmak'}
  };
  Object.entries(V5_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const V6_I18N = {
    ru:{links:'Ссылки',linksSettings:'Ссылки профиля',linksSettingsHint:'Здесь меняются кнопки «Поддержка» и «Чат» в профиле пользователя.',supportLink:'Ссылка поддержки',chatLink:'Ссылка на чат',saveLinks:'Сохранить ссылки',linksSaved:'Ссылки сохранены',openLink:'Открыть',invalidUrl:'Укажите корректную ссылку http(s):// или tg://',profitCalculator:'Калькулятор прибыли',profitCalculatorHint:'Расчёт по текущей ставке и сроку NOVERA.',investmentAmount:'Сумма депозита',dailyProfit:'Прибыль в день',termProfit:'Прибыль за срок',depositReturn:'Возврат депозита',totalReturn:'Всего к получению',finalDayPayment:'Выплата в последний день',profitCalcNote:'Ежедневно выплачивается прибыль. В последний день отдельно возвращается тело депозита.',goToDeposit:'Перейти к пополнению',depositRange:'Допустимая сумма'},
    en:{links:'Links',linksSettings:'Profile links',linksSettingsHint:'Change the Support and Chat buttons shown in the user profile.',supportLink:'Support link',chatLink:'Chat link',saveLinks:'Save links',linksSaved:'Links saved',openLink:'Open',invalidUrl:'Enter a valid http(s):// or tg:// URL',profitCalculator:'Profit calculator',profitCalculatorHint:'Calculated from the current NOVERA rate and term.',investmentAmount:'Deposit amount',dailyProfit:'Daily profit',termProfit:'Profit for the term',depositReturn:'Principal return',totalReturn:'Total to receive',finalDayPayment:'Final-day payout',profitCalcNote:'Profit is paid daily. The principal is returned separately on the final day.',goToDeposit:'Go to deposit',depositRange:'Allowed amount'},
    uk:{links:'Посилання',linksSettings:'Посилання профілю',linksSettingsHint:'Тут змінюються кнопки «Підтримка» і «Чат» у профілі користувача.',supportLink:'Посилання підтримки',chatLink:'Посилання на чат',saveLinks:'Зберегти посилання',linksSaved:'Посилання збережено',openLink:'Відкрити',invalidUrl:'Вкажіть коректне посилання http(s):// або tg://',profitCalculator:'Калькулятор прибутку',profitCalculatorHint:'Розрахунок за поточною ставкою та строком NOVERA.',investmentAmount:'Сума депозиту',dailyProfit:'Прибуток на день',termProfit:'Прибуток за строк',depositReturn:'Повернення депозиту',totalReturn:'Всього до отримання',finalDayPayment:'Виплата в останній день',profitCalcNote:'Прибуток виплачується щодня. В останній день окремо повертається тіло депозиту.',goToDeposit:'Перейти до поповнення',depositRange:'Допустима сума'},
    bg:{links:'Връзки',linksSettings:'Връзки в профила',linksSettingsHint:'Тук се променят бутоните „Поддръжка“ и „Чат“ в профила.',supportLink:'Линк за поддръжка',chatLink:'Линк към чата',saveLinks:'Запази връзките',linksSaved:'Връзките са запазени',openLink:'Отвори',invalidUrl:'Въведете валиден http(s):// или tg:// адрес',profitCalculator:'Калкулатор на печалбата',profitCalculatorHint:'Изчисление по текущата ставка и срок на NOVERA.',investmentAmount:'Сума на депозита',dailyProfit:'Печалба на ден',termProfit:'Печалба за срока',depositReturn:'Връщане на депозита',totalReturn:'Общо за получаване',finalDayPayment:'Плащане в последния ден',profitCalcNote:'Печалбата се изплаща ежедневно. В последния ден главницата се връща отделно.',goToDeposit:'Към депозит',depositRange:'Допустима сума'},
    kk:{links:'Сілтемелер',linksSettings:'Профиль сілтемелері',linksSettingsHint:'Мұнда профильдегі «Қолдау» және «Чат» батырмаларының сілтемелері өзгереді.',supportLink:'Қолдау сілтемесі',chatLink:'Чат сілтемесі',saveLinks:'Сілтемелерді сақтау',linksSaved:'Сілтемелер сақталды',openLink:'Ашу',invalidUrl:'Дұрыс http(s):// немесе tg:// сілтемесін енгізіңіз',profitCalculator:'Пайда калькуляторы',profitCalculatorHint:'NOVERA ағымдағы мөлшерлемесі мен мерзімі бойынша есеп.',investmentAmount:'Депозит сомасы',dailyProfit:'Күндік пайда',termProfit:'Мерзімдегі пайда',depositReturn:'Депозитті қайтару',totalReturn:'Жалпы алынатын сома',finalDayPayment:'Соңғы күнгі төлем',profitCalcNote:'Пайда күн сайын төленеді. Соңғы күні депозит сомасы бөлек қайтарылады.',goToDeposit:'Толтыруға өту',depositRange:'Рұқсат етілген сома'},
    be:{links:'Спасылкі',linksSettings:'Спасылкі профілю',linksSettingsHint:'Тут змяняюцца кнопкі «Падтрымка» і «Чат» у профілі.',supportLink:'Спасылка падтрымкі',chatLink:'Спасылка на чат',saveLinks:'Захаваць спасылкі',linksSaved:'Спасылкі захаваны',openLink:'Адкрыць',invalidUrl:'Укажыце карэктную спасылку http(s):// або tg://',profitCalculator:'Калькулятар прыбытку',profitCalculatorHint:'Разлік па бягучай стаўцы і тэрміне NOVERA.',investmentAmount:'Сума дэпазіту',dailyProfit:'Прыбытак у дзень',termProfit:'Прыбытак за тэрмін',depositReturn:'Вяртанне дэпазіту',totalReturn:'Усяго да атрымання',finalDayPayment:'Выплата ў апошні дзень',profitCalcNote:'Прыбытак выплачваецца штодня. У апошні дзень асобна вяртаецца сума дэпазіту.',goToDeposit:'Перайсці да папаўнення',depositRange:'Дапушчальная сума'},
    es:{links:'Enlaces',linksSettings:'Enlaces del perfil',linksSettingsHint:'Aquí se cambian los botones Soporte y Chat del perfil.',supportLink:'Enlace de soporte',chatLink:'Enlace del chat',saveLinks:'Guardar enlaces',linksSaved:'Enlaces guardados',openLink:'Abrir',invalidUrl:'Introduce una URL válida http(s):// o tg://',profitCalculator:'Calculadora de ganancias',profitCalculatorHint:'Cálculo según la tasa y el plazo actuales de NOVERA.',investmentAmount:'Importe del depósito',dailyProfit:'Ganancia diaria',termProfit:'Ganancia del período',depositReturn:'Devolución del depósito',totalReturn:'Total a recibir',finalDayPayment:'Pago del último día',profitCalcNote:'La ganancia se paga diariamente. El capital se devuelve por separado el último día.',goToDeposit:'Ir al depósito',depositRange:'Importe permitido'},
    it:{links:'Link',linksSettings:'Link del profilo',linksSettingsHint:'Qui si cambiano i pulsanti Supporto e Chat del profilo.',supportLink:'Link supporto',chatLink:'Link chat',saveLinks:'Salva link',linksSaved:'Link salvati',openLink:'Apri',invalidUrl:'Inserisci un URL valido http(s):// o tg://',profitCalculator:'Calcolatore profitto',profitCalculatorHint:'Calcolo basato sul tasso e sulla durata attuali di NOVERA.',investmentAmount:'Importo deposito',dailyProfit:'Profitto giornaliero',termProfit:'Profitto del periodo',depositReturn:'Rimborso deposito',totalReturn:'Totale da ricevere',finalDayPayment:'Pagamento dell’ultimo giorno',profitCalcNote:'Il profitto viene pagato ogni giorno. Il capitale viene restituito separatamente l’ultimo giorno.',goToDeposit:'Vai al deposito',depositRange:'Importo consentito'},
    tr:{links:'Bağlantılar',linksSettings:'Profil bağlantıları',linksSettingsHint:'Profildeki Destek ve Sohbet düğmelerinin bağlantıları burada değiştirilir.',supportLink:'Destek bağlantısı',chatLink:'Sohbet bağlantısı',saveLinks:'Bağlantıları kaydet',linksSaved:'Bağlantılar kaydedildi',openLink:'Aç',invalidUrl:'Geçerli bir http(s):// veya tg:// bağlantısı girin',profitCalculator:'Kâr hesaplayıcı',profitCalculatorHint:'NOVERA’un mevcut oranı ve süresine göre hesaplama.',investmentAmount:'Yatırım tutarı',dailyProfit:'Günlük kâr',termProfit:'Dönem kârı',depositReturn:'Ana para iadesi',totalReturn:'Toplam alınacak',finalDayPayment:'Son gün ödemesi',profitCalcNote:'Kâr günlük ödenir. Ana para son gün ayrıca iade edilir.',goToDeposit:'Yatırıma geç',depositRange:'İzin verilen tutar'},
    tk:{links:'Salgylamalar',linksSettings:'Profil salgylamalary',linksSettingsHint:'Profildäki Goldaw we Çat düwmeleriniň salgylamalary şu ýerde üýtgedilýär.',supportLink:'Goldaw salgysy',chatLink:'Çat salgysy',saveLinks:'Salgylamalary ýazdyr',linksSaved:'Salgylamalar ýazdyryldy',openLink:'Aç',invalidUrl:'Dogry http(s):// ýa-da tg:// salgysyny giriziň',profitCalculator:'Peýda kalkulýatory',profitCalculatorHint:'NOVERA häzirki göterimi we möhleti boýunça hasaplama.',investmentAmount:'Depozit möçberi',dailyProfit:'Günlük peýda',termProfit:'Möhlet peýdasy',depositReturn:'Depoziti gaýtarmak',totalReturn:'Jemi alynjak',finalDayPayment:'Soňky gün tölegi',profitCalcNote:'Peýda her gün tölenýär. Soňky gün depozitiň esasy möçberi aýratyn gaýtarylýar.',goToDeposit:'Depozite geç',depositRange:'Rugsat edilen möçber'}
  };
  Object.entries(V6_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const V8_I18N = {
    ru:{yourStats:'ВАША СТАТИСТИКА',referralStats:'Партнёрская статистика',referralIncome:'Доход от партнёрки',todayEarned:'Сегодня',yourInvestments:'Ваши инвестиции',lineTurnover:'Оборот линии',inTeam:'В команде',levelsUnlocked:'Уровни',nextGoal:'СЛЕДУЮЩАЯ ЦЕЛЬ',remaining:'Осталось',personalDeposit:'личного депозита',lineTurnoverGoal:'оборота линии',allLevelsUnlocked:'Все 5 уровней открыты',availableToWithdraw:'Доступно к выводу',withdrawalPending:'В обработке',withdrawReferral:'Вывести на кошелёк',withdrawMinHint:'Минимальная сумма вывода — 1 USDT. Выплата отправляется на кошелёк из профиля.',withdrawalRequested:'Вывод отправлен в обработку',setPayoutWalletFirst:'Сначала укажите кошелёк для выплат',referralMinimum:'Для вывода необходимо минимум 1 USDT',payoutsDisabled:'Выплаты временно отключены'},
    en:{yourStats:'YOUR STATISTICS',referralStats:'Partner statistics',referralIncome:'Referral income',todayEarned:'Today',yourInvestments:'Your investments',lineTurnover:'Line turnover',inTeam:'In team',levelsUnlocked:'Levels',nextGoal:'NEXT GOAL',remaining:'Remaining',personalDeposit:'personal deposit',lineTurnoverGoal:'line turnover',allLevelsUnlocked:'All 5 levels unlocked',availableToWithdraw:'Available to withdraw',withdrawalPending:'Processing',withdrawReferral:'Withdraw to wallet',withdrawMinHint:'Minimum withdrawal is 1 USDT. Funds are sent to the wallet saved in your profile.',withdrawalRequested:'Withdrawal queued for processing',setPayoutWalletFirst:'Set your payout wallet first',referralMinimum:'Minimum referral withdrawal is 1 USDT',payoutsDisabled:'Payouts are temporarily disabled'},
    uk:{yourStats:'ВАША СТАТИСТИКА',referralStats:'Партнерська статистика',referralIncome:'Дохід від партнерки',todayEarned:'Сьогодні',yourInvestments:'Ваші інвестиції',lineTurnover:'Оборот лінії',inTeam:'У команді',levelsUnlocked:'Рівні',nextGoal:'НАСТУПНА ЦІЛЬ',remaining:'Залишилось',personalDeposit:'особистого депозиту',lineTurnoverGoal:'обороту лінії',allLevelsUnlocked:'Усі 5 рівнів відкриті',availableToWithdraw:'Доступно до виведення',withdrawalPending:'В обробці',withdrawReferral:'Вивести на гаманець',withdrawMinHint:'Мінімальна сума виведення — 1 USDT. Виплата надсилається на гаманець із профілю.',withdrawalRequested:'Виведення передано в обробку',setPayoutWalletFirst:'Спочатку вкажіть гаманець для виплат',referralMinimum:'Для виведення потрібно щонайменше 1 USDT',payoutsDisabled:'Виплати тимчасово вимкнені'},
    bg:{yourStats:'ВАШАТА СТАТИСТИКА',referralStats:'Партньорска статистика',referralIncome:'Партньорски доход',todayEarned:'Днес',yourInvestments:'Вашите инвестиции',lineTurnover:'Оборот на линията',inTeam:'В екипа',levelsUnlocked:'Нива',nextGoal:'СЛЕДВАЩА ЦЕЛ',remaining:'Остава',personalDeposit:'личен депозит',lineTurnoverGoal:'оборот на линията',allLevelsUnlocked:'Всички 5 нива са отключени',availableToWithdraw:'Налично за теглене',withdrawalPending:'Обработва се',withdrawReferral:'Изтегли към портфейла',withdrawMinHint:'Минималното теглене е 1 USDT. Плащането се изпраща към портфейла в профила.',withdrawalRequested:'Тегленето е изпратено за обработка',setPayoutWalletFirst:'Първо задайте портфейл за плащания',referralMinimum:'Минималното теглене е 1 USDT',payoutsDisabled:'Плащанията са временно изключени'},
    kk:{yourStats:'СІЗДІҢ СТАТИСТИКА',referralStats:'Серіктестік статистика',referralIncome:'Серіктестік табыс',todayEarned:'Бүгін',yourInvestments:'Сіздің инвестициялар',lineTurnover:'Желі айналымы',inTeam:'Командада',levelsUnlocked:'Деңгейлер',nextGoal:'КЕЛЕСІ МАҚСАТ',remaining:'Қалды',personalDeposit:'жеке депозит',lineTurnoverGoal:'желі айналымы',allLevelsUnlocked:'Барлық 5 деңгей ашық',availableToWithdraw:'Шығаруға қолжетімді',withdrawalPending:'Өңделуде',withdrawReferral:'Әмиянға шығару',withdrawMinHint:'Ең аз шығару сомасы — 1 USDT. Төлем профильдегі әмиянға жіберіледі.',withdrawalRequested:'Шығару өңдеуге жіберілді',setPayoutWalletFirst:'Алдымен төлем әмиянын көрсетіңіз',referralMinimum:'Шығару үшін кемінде 1 USDT қажет',payoutsDisabled:'Төлемдер уақытша өшірілген'},
    be:{yourStats:'ВАША СТАТЫСТЫКА',referralStats:'Партнёрская статыстыка',referralIncome:'Партнёрскі даход',todayEarned:'Сёння',yourInvestments:'Вашы інвестыцыі',lineTurnover:'Абарот лініі',inTeam:'У камандзе',levelsUnlocked:'Узроўні',nextGoal:'НАСТУПНАЯ МЭТА',remaining:'Засталося',personalDeposit:'асабістага дэпазіту',lineTurnoverGoal:'абароту лініі',allLevelsUnlocked:'Усе 5 узроўняў адкрыты',availableToWithdraw:'Даступна да вываду',withdrawalPending:'Апрацоўваецца',withdrawReferral:'Вывесці на кашалёк',withdrawMinHint:'Мінімальны вывад — 1 USDT. Выплата адпраўляецца на кашалёк з профілю.',withdrawalRequested:'Вывад перададзены ў апрацоўку',setPayoutWalletFirst:'Спачатку ўкажыце кашалёк для выплат',referralMinimum:'Для вываду патрэбна мінімум 1 USDT',payoutsDisabled:'Выплаты часова адключаны'},
    es:{yourStats:'TUS ESTADÍSTICAS',referralStats:'Estadísticas de socios',referralIncome:'Ingresos por referidos',todayEarned:'Hoy',yourInvestments:'Tus inversiones',lineTurnover:'Volumen de línea',inTeam:'En el equipo',levelsUnlocked:'Niveles',nextGoal:'SIGUIENTE OBJETIVO',remaining:'Falta',personalDeposit:'depósito personal',lineTurnoverGoal:'volumen de línea',allLevelsUnlocked:'Los 5 niveles están desbloqueados',availableToWithdraw:'Disponible para retirar',withdrawalPending:'Procesando',withdrawReferral:'Retirar a la cartera',withdrawMinHint:'El retiro mínimo es 1 USDT. El pago se envía a la cartera guardada en tu perfil.',withdrawalRequested:'Retiro enviado a procesamiento',setPayoutWalletFirst:'Primero configura la cartera de pagos',referralMinimum:'El retiro mínimo es 1 USDT',payoutsDisabled:'Los pagos están temporalmente desactivados'},
    it:{yourStats:'LE TUE STATISTICHE',referralStats:'Statistiche partner',referralIncome:'Entrate referral',todayEarned:'Oggi',yourInvestments:'I tuoi investimenti',lineTurnover:'Volume linea',inTeam:'Nel team',levelsUnlocked:'Livelli',nextGoal:'PROSSIMO OBIETTIVO',remaining:'Manca',personalDeposit:'deposito personale',lineTurnoverGoal:'volume linea',allLevelsUnlocked:'Tutti e 5 i livelli sbloccati',availableToWithdraw:'Disponibile al prelievo',withdrawalPending:'In elaborazione',withdrawReferral:'Preleva sul wallet',withdrawMinHint:'Il prelievo minimo è 1 USDT. Il pagamento viene inviato al wallet salvato nel profilo.',withdrawalRequested:'Prelievo inviato in elaborazione',setPayoutWalletFirst:'Imposta prima il wallet per i pagamenti',referralMinimum:'Il prelievo minimo è 1 USDT',payoutsDisabled:'I pagamenti sono temporaneamente disattivati'},
    tr:{yourStats:'İSTATİSTİKLERİNİZ',referralStats:'Ortaklık istatistikleri',referralIncome:'Referans geliri',todayEarned:'Bugün',yourInvestments:'Yatırımlarınız',lineTurnover:'Hat hacmi',inTeam:'Ekipte',levelsUnlocked:'Seviyeler',nextGoal:'SONRAKİ HEDEF',remaining:'Kalan',personalDeposit:'kişisel yatırım',lineTurnoverGoal:'hat hacmi',allLevelsUnlocked:'5 seviyenin tümü açık',availableToWithdraw:'Çekilebilir',withdrawalPending:'İşleniyor',withdrawReferral:'Cüzdana çek',withdrawMinHint:'Minimum çekim 1 USDT. Ödeme profilinizdeki cüzdana gönderilir.',withdrawalRequested:'Çekim işleme alındı',setPayoutWalletFirst:'Önce ödeme cüzdanını ayarlayın',referralMinimum:'Minimum referans çekimi 1 USDT',payoutsDisabled:'Ödemeler geçici olarak devre dışı'},
    tk:{yourStats:'SIZIŇ STATISTIKAŇYZ',referralStats:'Hyzmatdaş statistikasy',referralIncome:'Referal girdejisi',todayEarned:'Şu gün',yourInvestments:'Siziň maýa goýumlaryňyz',lineTurnover:'Setir dolanyşygy',inTeam:'Toparda',levelsUnlocked:'Derejeler',nextGoal:'INDIKI MAKSAT',remaining:'Galdy',personalDeposit:'şahsy depozit',lineTurnoverGoal:'setir dolanyşygy',allLevelsUnlocked:'Ähli 5 dereje açyk',availableToWithdraw:'Çykarmaga elýeterli',withdrawalPending:'Işlenýär',withdrawReferral:'Gapjyga çykarmak',withdrawMinHint:'Iň az çykaryş 1 USDT. Töleg profildäki gapjyga iberilýär.',withdrawalRequested:'Çykaryş işlenmäge iberildi',setPayoutWalletFirst:'Ilki töleg gapjygyny görkeziň',referralMinimum:'Çykarmak üçin azyndan 1 USDT gerek',payoutsDisabled:'Tölegler wagtlaýyn öçürilen'}
  };
  Object.entries(V8_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const INVITER_ADMIN_I18N = {
    ru:{inviterManagement:'Партнёрская привязка',currentInviter:'Текущий пригласитель',newInviter:'Новый пригласитель',inviterIdentifier:'Telegram ID или @username',setInviter:'Сменить пригласителя',clearInviter:'Убрать пригласителя',inviterChangeHint:'Изменение действует на структуру и будущие партнёрские начисления. Уже начисленные и выплаченные вознаграждения не переносятся.',inviterChanged:'Пригласитель изменён',inviterCleared:'Пригласитель удалён',inviterHistory:'История смены пригласителя',noInviterHistory:'Пригласитель администратором ещё не менялся.',from:'Было',to:'Стало',referrerNotFound:'Пригласитель не найден',referrerCycle:'Нельзя выбрать пользователя из его собственной структуры',referrerSelf:'Пользователь не может пригласить сам себя',ambiguousReferrer:'Такой @username встречается несколько раз. Используйте Telegram ID.',confirmInviterChange:'Изменить пригласителя? Структура пользователя будет перенесена под нового пригласителя. Исторические начисления останутся без изменений.'},
    en:{inviterManagement:'Partner binding',currentInviter:'Current referrer',newInviter:'New referrer',inviterIdentifier:'Telegram ID or @username',setInviter:'Change referrer',clearInviter:'Remove referrer',inviterChangeHint:'The change affects the structure and future referral accruals. Existing accruals and paid rewards are not moved.',inviterChanged:'Referrer changed',inviterCleared:'Referrer removed',inviterHistory:'Referrer change history',noInviterHistory:'The referrer has not been changed by an administrator.',from:'From',to:'To',referrerNotFound:'Referrer not found',referrerCycle:'You cannot select a user from this user’s own downline',referrerSelf:'A user cannot refer themselves',ambiguousReferrer:'This @username matches multiple records. Use Telegram ID.',confirmInviterChange:'Change the referrer? This user’s subtree will move under the new referrer. Historical rewards remain unchanged.'},
    uk:{inviterManagement:'Партнерська прив’язка',currentInviter:'Поточний запрошувач',newInviter:'Новий запрошувач',inviterIdentifier:'Telegram ID або @username',setInviter:'Змінити запрошувача',clearInviter:'Прибрати запрошувача',inviterChangeHint:'Зміна впливає на структуру та майбутні партнерські нарахування. Уже нараховані та виплачені винагороди не переносяться.',inviterChanged:'Запрошувача змінено',inviterCleared:'Запрошувача видалено',inviterHistory:'Історія зміни запрошувача',noInviterHistory:'Адміністратор ще не змінював запрошувача.',from:'Було',to:'Стало',referrerNotFound:'Запрошувача не знайдено',referrerCycle:'Не можна вибрати користувача з його власної структури',referrerSelf:'Користувач не може запросити сам себе',ambiguousReferrer:'Цей @username зустрічається кілька разів. Використайте Telegram ID.',confirmInviterChange:'Змінити запрошувача? Структура користувача перейде під нового запрошувача. Історичні нарахування не зміняться.'},
    bg:{inviterManagement:'Партньорско свързване',currentInviter:'Текущ поканил',newInviter:'Нов поканил',inviterIdentifier:'Telegram ID или @username',setInviter:'Смени поканилия',clearInviter:'Премахни поканилия',inviterChangeHint:'Промяната засяга структурата и бъдещите партньорски начисления. Вече начислените и изплатени награди не се прехвърлят.',inviterChanged:'Поканилият е сменен',inviterCleared:'Поканилият е премахнат',inviterHistory:'История на промените',noInviterHistory:'Поканилият още не е променян от администратор.',from:'От',to:'Към',referrerNotFound:'Поканилият не е намерен',referrerCycle:'Не може да изберете потребител от собствената структура',referrerSelf:'Потребителят не може да покани себе си',ambiguousReferrer:'Този @username съвпада с няколко записа. Използвайте Telegram ID.',confirmInviterChange:'Да се смени ли поканилият? Структурата на потребителя ще се премести под новия поканил. Историческите награди остават без промяна.'},
    kk:{inviterManagement:'Серіктестік байланыс',currentInviter:'Қазіргі шақырушы',newInviter:'Жаңа шақырушы',inviterIdentifier:'Telegram ID немесе @username',setInviter:'Шақырушыны өзгерту',clearInviter:'Шақырушыны алып тастау',inviterChangeHint:'Өзгеріс құрылымға және болашақ серіктестік есептеулерге әсер етеді. Бұрын есептелген және төленген сыйақылар көшірілмейді.',inviterChanged:'Шақырушы өзгертілді',inviterCleared:'Шақырушы жойылды',inviterHistory:'Шақырушы өзгерістерінің тарихы',noInviterHistory:'Әкімші шақырушыны әлі өзгерткен жоқ.',from:'Бұрын',to:'Қазір',referrerNotFound:'Шақырушы табылмады',referrerCycle:'Пайдаланушының өз құрылымындағы адамды таңдауға болмайды',referrerSelf:'Пайдаланушы өзін өзі шақыра алмайды',ambiguousReferrer:'Бұл @username бірнеше жазбаға сәйкес келеді. Telegram ID пайдаланыңыз.',confirmInviterChange:'Шақырушыны өзгерту керек пе? Пайдаланушы құрылымы жаңа шақырушының астына көшеді. Тарихи сыйақылар өзгермейді.'},
    be:{inviterManagement:'Партнёрская прывязка',currentInviter:'Бягучы запрашальнік',newInviter:'Новы запрашальнік',inviterIdentifier:'Telegram ID або @username',setInviter:'Змяніць запрашальніка',clearInviter:'Выдаліць запрашальніка',inviterChangeHint:'Змена ўплывае на структуру і будучыя партнёрскія налічэнні. Ужо налічаныя і выплачаныя ўзнагароды не пераносяцца.',inviterChanged:'Запрашальнік зменены',inviterCleared:'Запрашальнік выдалены',inviterHistory:'Гісторыя змен запрашальніка',noInviterHistory:'Адміністратар яшчэ не змяняў запрашальніка.',from:'Было',to:'Стала',referrerNotFound:'Запрашальнік не знойдзены',referrerCycle:'Нельга выбраць карыстальніка з яго ўласнай структуры',referrerSelf:'Карыстальнік не можа запрасіць сам сябе',ambiguousReferrer:'Гэты @username адпавядае некалькім запісам. Выкарыстоўвайце Telegram ID.',confirmInviterChange:'Змяніць запрашальніка? Структура карыстальніка пяройдзе пад новага запрашальніка. Гістарычныя налічэнні не зменяцца.'},
    es:{inviterManagement:'Vinculación de socio',currentInviter:'Referente actual',newInviter:'Nuevo referente',inviterIdentifier:'Telegram ID o @username',setInviter:'Cambiar referente',clearInviter:'Quitar referente',inviterChangeHint:'El cambio afecta a la estructura y a las futuras comisiones. Las comisiones ya acumuladas o pagadas no se trasladan.',inviterChanged:'Referente cambiado',inviterCleared:'Referente eliminado',inviterHistory:'Historial de cambios',noInviterHistory:'El referente aún no ha sido cambiado por un administrador.',from:'Antes',to:'Después',referrerNotFound:'Referente no encontrado',referrerCycle:'No se puede elegir a un usuario de su propia estructura',referrerSelf:'Un usuario no puede referirse a sí mismo',ambiguousReferrer:'Este @username coincide con varios registros. Usa Telegram ID.',confirmInviterChange:'¿Cambiar el referente? La estructura del usuario se moverá bajo el nuevo referente. Las recompensas históricas no cambiarán.'},
    it:{inviterManagement:'Collegamento partner',currentInviter:'Referrer attuale',newInviter:'Nuovo referrer',inviterIdentifier:'Telegram ID o @username',setInviter:'Cambia referrer',clearInviter:'Rimuovi referrer',inviterChangeHint:'La modifica influisce sulla struttura e sui futuri accrediti referral. Gli accrediti e i pagamenti già registrati non vengono trasferiti.',inviterChanged:'Referrer modificato',inviterCleared:'Referrer rimosso',inviterHistory:'Cronologia modifiche referrer',noInviterHistory:'Il referrer non è ancora stato modificato da un amministratore.',from:'Prima',to:'Dopo',referrerNotFound:'Referrer non trovato',referrerCycle:'Non puoi scegliere un utente della sua stessa struttura',referrerSelf:'Un utente non può essere il proprio referrer',ambiguousReferrer:'Questo @username corrisponde a più record. Usa Telegram ID.',confirmInviterChange:'Cambiare il referrer? La struttura dell’utente verrà spostata sotto il nuovo referrer. Le ricompense storiche restano invariate.'},
    tr:{inviterManagement:'Ortaklık bağlantısı',currentInviter:'Mevcut davet eden',newInviter:'Yeni davet eden',inviterIdentifier:'Telegram ID veya @username',setInviter:'Davet edeni değiştir',clearInviter:'Davet edeni kaldır',inviterChangeHint:'Değişiklik yapıyı ve gelecekteki ortaklık kazançlarını etkiler. Daha önce tahakkuk eden veya ödenen ödüller taşınmaz.',inviterChanged:'Davet eden değiştirildi',inviterCleared:'Davet eden kaldırıldı',inviterHistory:'Davet eden değişiklik geçmişi',noInviterHistory:'Davet eden henüz yönetici tarafından değiştirilmedi.',from:'Önce',to:'Sonra',referrerNotFound:'Davet eden bulunamadı',referrerCycle:'Kullanıcının kendi alt yapısından biri seçilemez',referrerSelf:'Kullanıcı kendisini davet edemez',ambiguousReferrer:'Bu @username birden fazla kayıtla eşleşiyor. Telegram ID kullanın.',confirmInviterChange:'Davet eden değiştirilsin mi? Kullanıcının alt yapısı yeni davet edenin altına taşınır. Geçmiş ödüller değişmez.'},
    tk:{inviterManagement:'Hyzmatdaş baglanyşygy',currentInviter:'Häzirki çakylykçy',newInviter:'Täze çakylykçy',inviterIdentifier:'Telegram ID ýa-da @username',setInviter:'Çakylykçyny üýtget',clearInviter:'Çakylykçyny aýyr',inviterChangeHint:'Üýtgeşme gurluşa we geljekki referal hasaplamalaryna täsir edýär. Öň hasaplanan ýa-da tölenen sylaglar geçirilmeýär.',inviterChanged:'Çakylykçy üýtgedildi',inviterCleared:'Çakylykçy aýryldy',inviterHistory:'Çakylykçynyň üýtgeşme taryhy',noInviterHistory:'Çakylykçy administrator tarapyndan entek üýtgedilmedi.',from:'Öň',to:'Soň',referrerNotFound:'Çakylykçy tapylmady',referrerCycle:'Ulanyjynyň öz gurluşyndaky adamy saýlap bolmaýar',referrerSelf:'Ulanyjy özüni özi çagyryp bilmeýär',ambiguousReferrer:'Bu @username birnäçe ýazga gabat gelýär. Telegram ID ulanyň.',confirmInviterChange:'Çakylykçy üýtgedilsinmi? Ulanyjynyň gurluşy täze çakylykçynyň aşagyna geçer. Öňki sylaglar üýtgemez.'}
  };
  Object.entries(INVITER_ADMIN_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));
  const TEST_PAYOUT_I18N = {
    ru:{testPayout:'Тестовая выплата',testPayoutTitle:'Реальная тестовая выплата',testPayoutHint:'Проверка реального автовывода тем же payout-worker, который обслуживает выплаты пользователей. Минимум — 1 USDT.',testPayoutWarning:'Это реальная необратимая транзакция из казны. Указанная сумма USDT будет отправлена на введённый BSC-кошелёк.',testPayoutAddress:'Кошелёк получателя',testPayoutAmount:'Сумма USDT',testPayoutAcknowledge:'Я понимаю, что USDT будут реально отправлены из казны',testPayoutSend:'Запустить реальную выплату',testPayoutQueued:'Тестовая выплата поставлена в очередь автовывода',testPayoutHistory:'Последние тестовые выплаты',testPayoutNone:'Тестовых выплат ещё не было.',testPayoutMinimum:'Минимальная тестовая выплата — 1 USDT',testPayoutSameWallet:'Для теста укажите кошелёк, отличный от казны',treasuryInsufficientUsdt:'Недостаточно USDT в казне',treasuryNoGas:'В казне нет BNB для комиссии сети',realPayoutsDisabled:'Реальные blockchain-выплаты не настроены',testPayoutConfirmDialog:'Подтвердить РЕАЛЬНУЮ выплату {amount} USDT на {address}? Отменить blockchain-транзакцию после отправки невозможно.',openExplorer:'Открыть транзакцию'},
    en:{testPayout:'Test payout',testPayoutTitle:'Real test payout',testPayoutHint:'Tests the same automatic payout worker used for user withdrawals. Minimum: 1 USDT.',testPayoutWarning:'This is a real irreversible treasury transaction. The entered USDT amount will be sent to the specified BSC wallet.',testPayoutAddress:'Recipient wallet',testPayoutAmount:'USDT amount',testPayoutAcknowledge:'I understand that real USDT will leave the treasury',testPayoutSend:'Run real payout',testPayoutQueued:'Test payout queued for automatic withdrawal',testPayoutHistory:'Recent test payouts',testPayoutNone:'No test payouts yet.',testPayoutMinimum:'Minimum test payout is 1 USDT',testPayoutSameWallet:'Use a wallet different from the treasury',treasuryInsufficientUsdt:'Treasury has insufficient USDT',treasuryNoGas:'Treasury has no BNB for network gas',realPayoutsDisabled:'Real blockchain payouts are not configured',testPayoutConfirmDialog:'Confirm REAL payout of {amount} USDT to {address}? A blockchain transaction cannot be reversed after broadcast.',openExplorer:'Open transaction'},
    uk:{testPayout:'Тестова виплата',testPayoutTitle:'Реальна тестова виплата',testPayoutHint:'Перевірка тим самим автоматичним payout-worker. Мінімум — 1 USDT.',testPayoutWarning:'Це реальна незворотна транзакція з казни.',testPayoutAddress:'Гаманець отримувача',testPayoutAmount:'Сума USDT',testPayoutAcknowledge:'Я розумію, що USDT реально будуть відправлені з казни',testPayoutSend:'Запустити реальну виплату',testPayoutQueued:'Тестову виплату поставлено в чергу',testPayoutHistory:'Останні тестові виплати',testPayoutNone:'Тестових виплат ще не було.',testPayoutMinimum:'Мінімальна тестова виплата — 1 USDT',treasuryInsufficientUsdt:'Недостатньо USDT у казні',treasuryNoGas:'У казні немає BNB для комісії',realPayoutsDisabled:'Реальні blockchain-виплати не налаштовані',openExplorer:'Відкрити транзакцію'},
    bg:{testPayout:'Тестово плащане',testPayoutTitle:'Реално тестово плащане',testPayoutHint:'Проверява същия автоматичен payout-worker. Минимум 1 USDT.',testPayoutWarning:'Това е реална необратима транзакция от хазната.',testPayoutAddress:'Портфейл на получателя',testPayoutAmount:'Сума USDT',testPayoutAcknowledge:'Разбирам, че реални USDT ще бъдат изпратени',testPayoutSend:'Пусни реално плащане',testPayoutQueued:'Тестовото плащане е поставено на опашка',testPayoutHistory:'Последни тестови плащания',testPayoutNone:'Няма тестови плащания.',testPayoutMinimum:'Минимумът е 1 USDT',treasuryInsufficientUsdt:'Недостатъчно USDT в хазната',treasuryNoGas:'Няма BNB за gas',realPayoutsDisabled:'Реалните blockchain плащания не са настроени',openExplorer:'Отвори транзакцията'},
    kk:{testPayout:'Тест төлемі',testPayoutTitle:'Нақты тест төлемі',testPayoutHint:'Сол автоматты payout-worker арқылы тексеру. Минимум 1 USDT.',testPayoutWarning:'Бұл қазынадан жасалатын нақты қайтарылмайтын транзакция.',testPayoutAddress:'Алушы әмияны',testPayoutAmount:'USDT сомасы',testPayoutAcknowledge:'USDT қазынадан нақты жіберілетінін түсінемін',testPayoutSend:'Нақты төлемді іске қосу',testPayoutQueued:'Тест төлемі кезекке қойылды',testPayoutHistory:'Соңғы тест төлемдері',testPayoutNone:'Тест төлемдері жоқ.',testPayoutMinimum:'Минимум 1 USDT',treasuryInsufficientUsdt:'Қазынада USDT жеткіліксіз',treasuryNoGas:'Gas үшін BNB жоқ',realPayoutsDisabled:'Нақты blockchain төлемдері бапталмаған',openExplorer:'Транзакцияны ашу'},
    be:{testPayout:'Тэставая выплата',testPayoutTitle:'Рэальная тэставая выплата',testPayoutHint:'Праверка тым жа аўтаматычным payout-worker. Мінімум 1 USDT.',testPayoutWarning:'Гэта рэальная незваротная транзакцыя з казны.',testPayoutAddress:'Кашалёк атрымальніка',testPayoutAmount:'Сума USDT',testPayoutAcknowledge:'Я разумею, што USDT будуць рэальна адпраўлены',testPayoutSend:'Запусціць рэальную выплату',testPayoutQueued:'Тэставая выплата ў чарзе',testPayoutHistory:'Апошнія тэставыя выплаты',testPayoutNone:'Тэставых выплат няма.',testPayoutMinimum:'Мінімум 1 USDT',treasuryInsufficientUsdt:'Недастаткова USDT у казне',treasuryNoGas:'Няма BNB для камісіі',realPayoutsDisabled:'Рэальныя blockchain-выплаты не настроены',openExplorer:'Адкрыць транзакцыю'},
    es:{testPayout:'Pago de prueba',testPayoutTitle:'Pago real de prueba',testPayoutHint:'Prueba el mismo payout-worker automático. Mínimo 1 USDT.',testPayoutWarning:'Es una transacción real e irreversible desde la tesorería.',testPayoutAddress:'Wallet destinataria',testPayoutAmount:'Cantidad USDT',testPayoutAcknowledge:'Entiendo que se enviarán USDT reales',testPayoutSend:'Ejecutar pago real',testPayoutQueued:'Pago de prueba en cola',testPayoutHistory:'Pagos de prueba recientes',testPayoutNone:'Aún no hay pagos de prueba.',testPayoutMinimum:'Mínimo 1 USDT',treasuryInsufficientUsdt:'USDT insuficiente en tesorería',treasuryNoGas:'No hay BNB para gas',realPayoutsDisabled:'Los pagos blockchain reales no están configurados',openExplorer:'Abrir transacción'},
    it:{testPayout:'Pagamento di prova',testPayoutTitle:'Pagamento reale di prova',testPayoutHint:'Testa lo stesso payout-worker automatico. Minimo 1 USDT.',testPayoutWarning:'È una transazione reale e irreversibile dalla tesoreria.',testPayoutAddress:'Wallet destinatario',testPayoutAmount:'Importo USDT',testPayoutAcknowledge:'Capisco che verranno inviati USDT reali',testPayoutSend:'Avvia pagamento reale',testPayoutQueued:'Pagamento di prova in coda',testPayoutHistory:'Pagamenti di prova recenti',testPayoutNone:'Nessun pagamento di prova.',testPayoutMinimum:'Minimo 1 USDT',treasuryInsufficientUsdt:'USDT insufficienti in tesoreria',treasuryNoGas:'BNB insufficiente per gas',realPayoutsDisabled:'I pagamenti blockchain reali non sono configurati',openExplorer:'Apri transazione'},
    tr:{testPayout:'Test ödemesi',testPayoutTitle:'Gerçek test ödemesi',testPayoutHint:'Aynı otomatik payout-worker ile test eder. Minimum 1 USDT.',testPayoutWarning:'Bu hazineden yapılan gerçek ve geri alınamaz bir işlemdir.',testPayoutAddress:'Alıcı cüzdanı',testPayoutAmount:'USDT tutarı',testPayoutAcknowledge:'Gerçek USDT gönderileceğini anlıyorum',testPayoutSend:'Gerçek ödemeyi başlat',testPayoutQueued:'Test ödemesi kuyruğa alındı',testPayoutHistory:'Son test ödemeleri',testPayoutNone:'Henüz test ödemesi yok.',testPayoutMinimum:'Minimum 1 USDT',treasuryInsufficientUsdt:'Hazinede yeterli USDT yok',treasuryNoGas:'Gas için BNB yok',realPayoutsDisabled:'Gerçek blockchain ödemeleri yapılandırılmamış',openExplorer:'İşlemi aç'},
    tk:{testPayout:'Synag tölegi',testPayoutTitle:'Hakyky synag tölegi',testPayoutHint:'Şol bir awtomat payout-worker arkaly synag. Minimum 1 USDT.',testPayoutWarning:'Bu gaznadan hakyky we yzyna gaýtaryp bolmaýan tranzaksiýa.',testPayoutAddress:'Alyjynyň gapjygy',testPayoutAmount:'USDT möçberi',testPayoutAcknowledge:'Hakyky USDT ugradylyp bilinjekdigine düşünýärin',testPayoutSend:'Hakyky tölegi başlat',testPayoutQueued:'Synag tölegi nobata goýuldy',testPayoutHistory:'Soňky synag tölegleri',testPayoutNone:'Synag tölegi ýok.',testPayoutMinimum:'Minimum 1 USDT',treasuryInsufficientUsdt:'Gaznada USDT ýeterlik däl',treasuryNoGas:'Gas üçin BNB ýok',realPayoutsDisabled:'Hakyky blockchain tölegleri sazlanmadyk',openExplorer:'Tranzaksiýany aç'}
  };
  Object.entries(TEST_PAYOUT_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const CAMPAIGNS_I18N = {
    ru:{
      promoCode:'Промокод',promoCodeOptionalHint:'Необязательно. Бонус начисляется один раз при первом депозите с этим кодом.',
      promoApplied:'Промокод применён: +{bonus} USDT бонуса. Итоговая сумма депозита: {total} USDT',promoInvalid:'Промокод недействителен или больше не активен',
      promoAlreadyRedeemed:'Вы уже использовали этот промокод',promoMinDepositError:'Сумма депозита меньше минимума для этого промокода',
      promoBonusLine:'Бонус по промокоду',promoEffectivePrincipalLine:'Итоговая сумма депозита',
      campaignsTab:'Кампании',
      newPromo:'Новый промокод',promoHint:'Бонус начисляется один раз пользователю при первом депозите с этим кодом.',
      promoBonusType:'Тип бонуса',promoBonusPercent:'% от депозита',promoBonusFixed:'Фикс. сумма USDT',promoBonusValue:'Значение бонуса',
      promoMaxRedemptions:'Лимит использований',promoMinDeposit:'Мин. депозит, USDT',createPromo:'Создать промокод',
      promoCodeRequired:'Введите код промокода',promoBonusInvalid:'Укажите положительное значение бонуса',promoMaxInvalid:'Лимит использований должен быть не меньше 1',
      promoCreated:'Промокод создан',promoNone:'Промокодов пока нет',promoUsed:'Использовано',
      enableAction:'Включить',disableAction:'Отключить',statusEnabled:'Включён',statusDisabled:'Отключён',
      promoEnabled:'Промокод включён',promoDisabled:'Промокод отключён',
      newCampaign:'Новая кампания',campaignHint:'Автоматическая рассылка по расписанию с опциональным промокодом.',
      campaignKind:'Тип кампании',campaignKindCustom:'Произвольная',campaignKindPromo:'Промокод',campaignKindPartner:'Партнёрская',
      campaignPromoSelect:'Промокод кампании',campaignPromoNone:'Без промокода',
      campaignScheduleMode:'Расписание',campaignScheduleInterval:'Интервал (часы)',campaignScheduleWeekly:'По дням недели',
      campaignIntervalHours:'Интервал, часов',campaignTimeUtc:'Время UTC (ЧЧ:MM)',campaignWeekdays:'Дни недели',
      weekdayMon:'Пн',weekdayTue:'Вт',weekdayWed:'Ср',weekdayThu:'Чт',weekdayFri:'Пт',weekdaySat:'Сб',weekdaySun:'Вс',
      campaignEnabled:'Кампания включена',createCampaign:'Создать кампанию',
      campaignMessageRequired:'Введите текст кампании',campaignPromoRequired:'Выберите промокод для кампании этого типа',
      campaignWeekdaysRequired:'Выберите хотя бы один день недели',campaignTimeInvalid:'Время должно быть в формате ЧЧ:MM',
      campaignCreated:'Кампания создана',campaignNone:'Кампаний пока нет',
      campaignEnabledNotice:'Кампания включена',campaignDisabledNotice:'Кампания отключена',
      runCampaignNow:'Запустить сейчас',campaignRunSent:'Рассылка кампании отправлена',campaignRunSkipped:'Кампания пропущена',
      campaignNextRun:'Следующий запуск',campaignLastRun:'Последний запуск'
    },
    en:{
      promoCode:'Promo code',promoCodeOptionalHint:'Optional. The bonus is granted once on the first deposit using this code.',
      promoApplied:'Promo applied: +{bonus} USDT bonus. Total deposit amount: {total} USDT',promoInvalid:'This promo code is invalid or no longer active',
      promoAlreadyRedeemed:'You already used this promo code',promoMinDepositError:'Deposit amount is below this promo minimum',
      promoBonusLine:'Promo bonus',promoEffectivePrincipalLine:'Total deposit amount',
      campaignsTab:'Campaigns',
      newPromo:'New promo code',promoHint:'The bonus is granted once per user on their first deposit using this code.',
      promoBonusType:'Bonus type',promoBonusPercent:'% of deposit',promoBonusFixed:'Fixed USDT amount',promoBonusValue:'Bonus value',
      promoMaxRedemptions:'Redemption limit',promoMinDeposit:'Min deposit, USDT',createPromo:'Create promo code',
      promoCodeRequired:'Enter a promo code',promoBonusInvalid:'Enter a positive bonus value',promoMaxInvalid:'Redemption limit must be at least 1',
      promoCreated:'Promo code created',promoNone:'No promo codes yet',promoUsed:'Used',
      enableAction:'Enable',disableAction:'Disable',statusEnabled:'Enabled',statusDisabled:'Disabled',
      promoEnabled:'Promo code enabled',promoDisabled:'Promo code disabled',
      newCampaign:'New campaign',campaignHint:'Automatic broadcast on a schedule, with an optional promo code.',
      campaignKind:'Campaign type',campaignKindCustom:'Custom',campaignKindPromo:'Promo',campaignKindPartner:'Partner',
      campaignPromoSelect:'Campaign promo code',campaignPromoNone:'No promo code',
      campaignScheduleMode:'Schedule',campaignScheduleInterval:'Interval (hours)',campaignScheduleWeekly:'Weekly days',
      campaignIntervalHours:'Interval, hours',campaignTimeUtc:'Time UTC (HH:MM)',campaignWeekdays:'Weekdays',
      weekdayMon:'Mon',weekdayTue:'Tue',weekdayWed:'Wed',weekdayThu:'Thu',weekdayFri:'Fri',weekdaySat:'Sat',weekdaySun:'Sun',
      campaignEnabled:'Campaign enabled',createCampaign:'Create campaign',
      campaignMessageRequired:'Enter the campaign message',campaignPromoRequired:'Select a promo code for this campaign type',
      campaignWeekdaysRequired:'Select at least one weekday',campaignTimeInvalid:'Time must use the HH:MM format',
      campaignCreated:'Campaign created',campaignNone:'No campaigns yet',
      campaignEnabledNotice:'Campaign enabled',campaignDisabledNotice:'Campaign disabled',
      runCampaignNow:'Run now',campaignRunSent:'Campaign broadcast sent',campaignRunSkipped:'Campaign run skipped',
      campaignNextRun:'Next run',campaignLastRun:'Last run'
    }
  };
  Object.entries(CAMPAIGNS_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const ADMIN_FINANCE_I18N = {
    ru:{referralBalanceControl:'Реферальный баланс',referralBalanceNote:'Доступная к выводу сумма. Изменение фиксируется в журнале и не переписывает прошлые начисления.',referralBalanceSaved:'Реферальный баланс изменён',referralBalanceHistory:'История реферального баланса',noReferralBalanceHistory:'Реферальный баланс администратором ещё не менялся.',manualInvestment:'Открыть инвестицию',manualInvestmentNote:'Создаёт активную инвестицию без blockchain-пополнения. Она запускает реальные выплаты по текущему графику; первая — через 24 часа.',openInvestment:'Открыть инвестицию',investmentOpened:'Инвестиция открыта',closeInvestment:'Закрыть инвестицию',closeInvestmentSection:'Закрытие инвестиции',closeInvestmentNote:'Останавливает активную инвестицию: будущие начисления не создаются, queued-выплаты отменяются. Уже confirmed on-chain выплаты не откатываются. Требуется причина ниже.',confirmCloseInvestment:'Закрыть инвестицию #{id}? Будущие выплаты будут остановлены.',investmentClosed:'Инвестиция закрыта',partnerLevelAccess:'Доступ к уровням партнёрки',partnerLevelNote:'Ручной уровень действует только на будущие начисления и открывает все предыдущие уровни. Уровень 0 возвращает автоматическую квалификацию.',automaticQualification:'0 — автоматически',levelAccessSaved:'Доступ к уровням сохранён',levelHistory:'История доступа к уровням',noLevelHistory:'Ручной доступ к уровням ещё не менялся.',adminReason:'Причина изменения',adminReasonHint:'Обязательный комментарий для журнала',confirmOpenInvestment:'Открыть инвестицию {amount} USDT? Это запустит реальные выплаты по стандартному графику.',userWalletRequired:'Сначала укажите пользователю кошелёк для выплат',adminSource:'Открыто администратором'},
    en:{referralBalanceControl:'Referral balance',referralBalanceNote:'Amount currently available for withdrawal. Changes are audited and do not rewrite past accruals.',referralBalanceSaved:'Referral balance updated',referralBalanceHistory:'Referral balance history',noReferralBalanceHistory:'The referral balance has not been changed by an administrator.',manualInvestment:'Open investment',manualInvestmentNote:'Creates an active investment without an on-chain deposit. It starts real payouts on the current schedule; the first is due in 24 hours.',openInvestment:'Open investment',investmentOpened:'Investment opened',closeInvestment:'Close investment',closeInvestmentSection:'Close investment',closeInvestmentNote:'Stops an active investment: no further accruals, queued payouts are cancelled. Confirmed on-chain payouts are not reversed. Reason below is required.',confirmCloseInvestment:'Close investment #{id}? Future payouts will stop.',investmentClosed:'Investment closed',partnerLevelAccess:'Partner level access',partnerLevelNote:'Manual access applies only to future accruals and includes all prior levels. Level 0 restores automatic qualification.',automaticQualification:'0 — automatic',levelAccessSaved:'Partner level access saved',levelHistory:'Level access history',noLevelHistory:'Manual level access has not been changed.',adminReason:'Change reason',adminReasonHint:'Required audit comment',confirmOpenInvestment:'Open a {amount} USDT investment? This starts real payouts on the standard schedule.',userWalletRequired:'Set the user payout wallet first',adminSource:'Opened by administrator'},
    uk:{referralBalanceControl:'Реферальний баланс',referralBalanceNote:'Доступна до виведення сума. Зміна фіксується в журналі та не переписує минулі нарахування.',referralBalanceSaved:'Реферальний баланс змінено',referralBalanceHistory:'Історія реферального балансу',noReferralBalanceHistory:'Баланс ще не змінювався адміністратором.',manualInvestment:'Відкрити інвестицію',manualInvestmentNote:'Створює активну інвестицію без blockchain-поповнення. Перша виплата — через 24 години.',openInvestment:'Відкрити інвестицію',investmentOpened:'Інвестицію відкрито',closeInvestment:'Закрити інвестицію',closeInvestmentSection:'Закриття інвестиції',closeInvestmentNote:'Зупиняє активну інвестицію: подальші нарахування не створюються, queued-виплати скасовуються. Confirmed on-chain виплати не відкатуються. Потрібна причина нижче.',confirmCloseInvestment:'Закрити інвестицію #{id}? Подальші виплати буде зупинено.',investmentClosed:'Інвестицію закрито',partnerLevelAccess:'Доступ до рівнів партнерки',partnerLevelNote:'Ручний рівень діє лише на майбутні нарахування та відкриває попередні рівні. Рівень 0 повертає автоматичну кваліфікацію.',automaticQualification:'0 — автоматично',levelAccessSaved:'Доступ до рівнів збережено',levelHistory:'Історія доступу до рівнів',noLevelHistory:'Ручний доступ ще не змінювався.',adminReason:'Причина зміни',adminReasonHint:'Обов’язковий коментар для журналу',confirmOpenInvestment:'Відкрити інвестицію {amount} USDT? Це запустить реальні виплати за стандартним графіком.',userWalletRequired:'Спочатку вкажіть гаманець користувача для виплат',adminSource:'Відкрито адміністратором'}
  };
  Object.entries(ADMIN_FINANCE_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const HOME_POSITION_I18N = {
    ru:{
      nextPayout:'Следующая выплата',nextPayoutNone:'Нет активных выплат',nextPayoutWithPrincipal:'включая возврат тела',
      receivedPaid:'Уже получено',receivedPaidHint:'подтверждённые выплаты',
      expectedRemaining:'Ожидается по графику',expectedHint:'прогноз · не баланс к выводу',
      partnerAvailableShort:'Партнёрка к выводу',partnerAvailableHint:'доступно сейчас',
      internalBalanceHint:'не прогноз выплат',
      assetPaid:'Выплачено',assetRemaining:'Осталось по графику',assetNextPayment:'Следующий платёж',
      assetIncludesPrincipal:'с возвратом тела'
    },
    en:{
      nextPayout:'Next payout',nextPayoutNone:'No active payouts',nextPayoutWithPrincipal:'includes principal return',
      receivedPaid:'Already received',receivedPaidHint:'confirmed payouts',
      expectedRemaining:'Scheduled remaining',expectedHint:'projection · not withdrawable',
      partnerAvailableShort:'Partner available',partnerAvailableHint:'withdrawable now',
      internalBalanceHint:'not payout projection',
      assetPaid:'Paid out',assetRemaining:'Remaining on schedule',assetNextPayment:'Next payment',
      assetIncludesPrincipal:'includes principal'
    },
    uk:{
      nextPayout:'Наступна виплата',nextPayoutNone:'Немає активних виплат',nextPayoutWithPrincipal:'з поверненням тіла',
      receivedPaid:'Вже отримано',receivedPaidHint:'підтверджені виплати',
      expectedRemaining:'Очікується за графіком',expectedHint:'прогноз · не баланс до виведення',
      partnerAvailableShort:'Партнерка до виведення',partnerAvailableHint:'доступно зараз',
      internalBalanceHint:'не прогноз виплат',
      assetPaid:'Виплачено',assetRemaining:'Залишилось за графіком',assetNextPayment:'Наступний платіж',
      assetIncludesPrincipal:'з поверненням тіла'
    }
  };
  Object.entries(HOME_POSITION_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const INVOICE_I18N = {
    ru:{
      depositNetworkLine:'USDT · BEP-20 · BNB Smart Chain',
      depositOnlyUsdt:'Только USDT в этой сети',
      setPayoutWalletBeforeDeposit:'Сначала сохраните кошелёк для выплат выше — без него заявку создать нельзя.',
      networkWarningText:'Отправляйте только USDT BEP-20 на показанный адрес и ровно ту сумму, которую сформировала заявка — включая уникальный хвост. Другая сеть или другая сумма не будут зачислены.',
      invoiceStatus:'Статус заявки',invoicePending:'Ожидает перевод',invoiceExpired:'Срок истёк',invoiceReused:'Повтор той же заявки',
      invoiceExactTitle:'Точная сумма к отправке',invoiceTailHint:'Сумма содержит уникальный хвост для сопоставления платежа. Отправьте её один в один.',
      invoiceAddressTitle:'Адрес казны',invoiceToken:'Токен',invoiceChainId:'Chain ID',
      invoiceCountdown:'Осталось',invoiceMinutes:'мин',invoiceSeconds:'сек',
      copyAddressDone:'Адрес скопирован',copyAmountDone:'Сумма скопирована',copyAllDone:'Реквизиты скопированы',
      depositsDisabledUi:'Пополнение временно недоступно',
      tooManyPendingInvoices:'Слишком много незакрытых заявок. Дождитесь зачисления или истечения срока.'
    },
    en:{
      depositNetworkLine:'USDT · BEP-20 · BNB Smart Chain',
      depositOnlyUsdt:'USDT only on this network',
      setPayoutWalletBeforeDeposit:'Save a payout wallet above first — an invoice cannot be created without it.',
      networkWarningText:'Send only USDT BEP-20 to the shown address for the exact invoice amount, including the unique fractional tail. Another network or amount will not credit.',
      invoiceStatus:'Invoice status',invoicePending:'Awaiting transfer',invoiceExpired:'Expired',invoiceReused:'Same invoice reused',
      invoiceExactTitle:'Exact amount to send',invoiceTailHint:'The amount includes a unique matching tail. Send it exactly as shown.',
      invoiceAddressTitle:'Treasury address',invoiceToken:'Token',invoiceChainId:'Chain ID',
      invoiceCountdown:'Time left',invoiceMinutes:'min',invoiceSeconds:'sec',
      copyAddressDone:'Address copied',copyAmountDone:'Amount copied',copyAllDone:'Payment details copied',
      depositsDisabledUi:'Deposits are temporarily unavailable',
      tooManyPendingInvoices:'Too many open invoices. Wait for credit or expiry.'
    },
    uk:{
      depositNetworkLine:'USDT · BEP-20 · BNB Smart Chain',
      depositOnlyUsdt:'Лише USDT у цій мережі',
      setPayoutWalletBeforeDeposit:'Спочатку збережіть гаманець для виплат вище — без нього заявку створити не можна.',
      networkWarningText:'Надсилайте лише USDT BEP-20 на показану адресу і рівно ту суму, яку сформувала заявка — включно з унікальним хвостом. Інша мережа або сума не будуть зараховані.',
      invoiceStatus:'Статус заявки',invoicePending:'Очікує переказ',invoiceExpired:'Термін минув',invoiceReused:'Повтор тієї ж заявки',
      invoiceExactTitle:'Точна сума до відправки',invoiceTailHint:'Сума містить унікальний хвіст для зіставлення платежу. Надішліть її один в один.',
      invoiceAddressTitle:'Адреса казни',invoiceToken:'Токен',invoiceChainId:'Chain ID',
      invoiceCountdown:'Залишилось',invoiceMinutes:'хв',invoiceSeconds:'сек',
      copyAddressDone:'Адресу скопійовано',copyAmountDone:'Суму скопійовано',copyAllDone:'Реквізити скопійовано',
      depositsDisabledUi:'Поповнення тимчасово недоступне',
      tooManyPendingInvoices:'Забагато відкритих заявок. Дочекайтесь зарахування або закінчення терміну.'
    }
  };
  Object.entries(INVOICE_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const ADMIN_USER_CARD_I18N = {
    ru:{
      userTabOverview:'Обзор',userTabInvestments:'Инвестиции',userTabPayouts:'Выплаты',userTabReferral:'Партнёрка',userTabAccess:'Доступ',userTabAudit:'Журнал',
      userOverviewHint:'Ключевые цифры и статус аккаунта.',userInvestmentsHint:'Ручное открытие и список депозитов.',userPayoutsHint:'Очередь и история выплат пользователя.',userReferralHint:'Рефбаланс, уровни и команда.',userAccessHint:'Кошелёк, пригласитель и блокировка.',userAuditHint:'История изменений с причинами.',
      noUserDeposits:'Депозитов у пользователя нет.',noUserPayouts:'Выплат у пользователя нет.',noUserPartners:'Прямых партнёров пока нет.',
      confirmSetBalance:'Изменить внутренний баланс? Причина сохранится в журнале.',
      confirmSetReferralBalance:'Изменить реферальный баланс? Причина сохранится в журнале.',
      confirmSetReferralLevel:'Изменить доступ к уровням партнёрки?',
      confirmClearWallet:'Очистить кошелёк выплат пользователя?',
      confirmBlockUser:'Заблокировать этого пользователя?',
      confirmUnblockUser:'Разблокировать этого пользователя?',
      partnerStatsTitle:'Партнёрская сводка',personalTurnover:'Личный оборот (все)',structureTurnover:'Оборот структуры (все)',structureMembers:'В структуре'
    },
    en:{
      userTabOverview:'Overview',userTabInvestments:'Investments',userTabPayouts:'Payouts',userTabReferral:'Referral',userTabAccess:'Access',userTabAudit:'Audit',
      userOverviewHint:'Key figures and account status.',userInvestmentsHint:'Manual open and deposit list.',userPayoutsHint:'User payout queue and history.',userReferralHint:'Referral balance, levels and team.',userAccessHint:'Wallet, inviter and block controls.',userAuditHint:'Change history with reasons.',
      noUserDeposits:'No deposits for this user.',noUserPayouts:'No payouts for this user.',noUserPartners:'No direct partners yet.',
      confirmSetBalance:'Change the internal balance? The reason is saved to the audit log.',
      confirmSetReferralBalance:'Change the referral balance? The reason is saved to the audit log.',
      confirmSetReferralLevel:'Change partner level access?',
      confirmClearWallet:'Clear this user payout wallet?',
      confirmBlockUser:'Block this user?',
      confirmUnblockUser:'Unblock this user?',
      partnerStatsTitle:'Partner summary',personalTurnover:'Personal turnover (all deposits)',structureTurnover:'Structure turnover (all deposits)',structureMembers:'In structure'
    },
    uk:{
      userTabOverview:'Огляд',userTabInvestments:'Інвестиції',userTabPayouts:'Виплати',userTabReferral:'Партнерка',userTabAccess:'Доступ',userTabAudit:'Журнал',
      userOverviewHint:'Ключові цифри та статус акаунта.',userInvestmentsHint:'Ручне відкриття і список депозитів.',userPayoutsHint:'Черга і історія виплат користувача.',userReferralHint:'Рефбаланс, рівні і команда.',userAccessHint:'Гаманець, запрошувач і блокування.',userAuditHint:'Історія змін із причинами.',
      noUserDeposits:'Депозитів у користувача немає.',noUserPayouts:'Виплат у користувача немає.',noUserPartners:'Прямих партнерів поки немає.',
      confirmSetBalance:'Змінити внутрішній баланс? Причина збережеться в журналі.',
      confirmSetReferralBalance:'Змінити реферальний баланс? Причина збережеться в журналі.',
      confirmSetReferralLevel:'Змінити доступ до рівнів партнерки?',
      confirmClearWallet:'Очистити гаманець виплат користувача?',
      confirmBlockUser:'Заблокувати цього користувача?',
      confirmUnblockUser:'Розблокувати цього користувача?',
      partnerStatsTitle:'Партнерська зведення',personalTurnover:'Особистий оборот (всі)',structureTurnover:'Оборот структури (всі)',structureMembers:'У структурі'
    }
  };
  Object.entries(ADMIN_USER_CARD_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const WALLET_IMPACT_I18N = {
    ru:{
      walletImpactLead:'Смена адреса влияет только на новые операции. Уже созданные выплаты и открытые депозиты сохраняют свой адрес.',
      walletImpactNew:'Новые пополнения и вывод партнёрского баланса — на этот адрес профиля.',
      walletImpactDeposits:'Открытые депозиты уже зафиксировали адрес при открытии; их график не переключается.',
      walletImpactPipeline:'Выплаты в статусах «в очереди / подписана / в сети» идут на адрес внутри самой выплаты — смена профиля их не меняет.',
      walletPipelineNone:'Открытых выплат (очередь / подпись / сеть) сейчас нет.',
      walletPipelineOpen:'Открытые выплаты: очередь {queued}, подписаны {signed}, в сети {broadcast}.',
      confirmSaveWallet:'Сохранить новый адрес выплат?\n\nУже созданные выплаты и открытые депозиты продолжат идти на старый зафиксированный адрес. Новый адрес — для будущих пополнений и вывода партнёрского баланса.',
      payoutAddressLabel:'Адрес выплаты',
      depositPayoutAddressLabel:'Адрес графика депозита',
      walletManagementHint:'Меняет только адрес профиля. Не переписывает queued/signed/broadcast и не меняет адрес уже открытых депозитов.',
      walletOpenStripTitle:'Открытые выплаты пользователя',
      confirmSaveAdminWallet:'Сменить кошелёк профиля?\n\nQueued / signed / broadcast и адреса открытых депозитов не изменятся. Новый адрес пойдёт только в новые депозиты и новые выводы рефбаланса.',
      confirmClearWallet:'Очистить кошелёк профиля?\n\nУже созданные выплаты и адреса открытых депозитов не изменятся. Новые депозиты и вывод рефбаланса станут недоступны, пока адрес снова не сохранят.',
      queued:'В очереди',signed:'Подписана',broadcast:'В сети',confirmed:'Подтверждена',
      withdrawMinHint:'Минимум вывода — 1 USDT. Средства уходят на текущий адрес профиля из раздела «Кошелёк».'
    },
    en:{
      walletImpactLead:'Changing the address only affects new operations. Existing payouts and open deposits keep their own address.',
      walletImpactNew:'New deposits and partner withdrawals use this profile address.',
      walletImpactDeposits:'Open deposits already froze an address when opened; their schedule does not switch.',
      walletImpactPipeline:'Payouts in queued / signed / broadcast keep the address stored on the payout itself — changing the profile does not rewrite them.',
      walletPipelineNone:'No open payouts (queued / signed / broadcast) right now.',
      walletPipelineOpen:'Open payouts: queued {queued}, signed {signed}, on-chain {broadcast}.',
      confirmSaveWallet:'Save a new payout address?\n\nExisting payouts and open deposits keep their frozen address. The new address is for future deposits and partner withdrawals.',
      payoutAddressLabel:'Payout address',
      depositPayoutAddressLabel:'Deposit schedule address',
      walletManagementHint:'Changes the profile address only. Does not rewrite queued/signed/broadcast or open-deposit addresses.',
      walletOpenStripTitle:'User open payouts',
      confirmSaveAdminWallet:'Change the profile wallet?\n\nQueued / signed / broadcast and open-deposit addresses stay unchanged. The new address applies only to new deposits and new referral withdrawals.',
      confirmClearWallet:'Clear the profile wallet?\n\nExisting payouts and open-deposit addresses stay unchanged. New deposits and referral withdrawals will be blocked until an address is saved again.',
      queued:'Queued',signed:'Signed',broadcast:'Broadcast',confirmed:'Confirmed',
      withdrawMinHint:'Minimum withdrawal is 1 USDT. Funds go to the current profile wallet from Wallet.'
    },
    uk:{
      walletImpactLead:'Зміна адреси впливає лише на нові операції. Вже створені виплати та відкриті депозити зберігають свою адресу.',
      walletImpactNew:'Нові поповнення і вивід партнерського балансу — на цю адресу профілю.',
      walletImpactDeposits:'Відкриті депозити вже зафіксували адресу при відкритті; їх графік не перемикається.',
      walletImpactPipeline:'Виплати в статусах «в черзі / підписана / в мережі» йдуть на адресу всередині самої виплати — зміна профілю їх не змінює.',
      walletPipelineNone:'Відкритих виплат (черга / підпис / мережа) зараз немає.',
      walletPipelineOpen:'Відкриті виплати: черга {queued}, підписані {signed}, в мережі {broadcast}.',
      confirmSaveWallet:'Зберегти нову адресу виплат?\n\nВже створені виплати та відкриті депозити продовжать іти на стару зафіксовану адресу. Нова адреса — для майбутніх поповнень і виводу партнерського балансу.',
      payoutAddressLabel:'Адреса виплати',
      depositPayoutAddressLabel:'Адреса графіка депозиту',
      walletManagementHint:'Змінює лише адресу профілю. Не переписує queued/signed/broadcast і не змінює адреси вже відкритих депозитів.',
      walletOpenStripTitle:'Відкриті виплати користувача',
      confirmSaveAdminWallet:'Змінити гаманець профілю?\n\nQueued / signed / broadcast та адреси відкритих депозитів не зміняться. Нова адреса піде лише в нові депозити і нові виводи рефбалансу.',
      confirmClearWallet:'Очистити гаманець профілю?\n\nВже створені виплати та адреси відкритих депозитів не зміняться. Нові депозити і вивід рефбалансу стануть недоступні, доки адресу знову не збережуть.',
      queued:'В черзі',signed:'Підписана',broadcast:'В мережі',confirmed:'Підтверджена',
      withdrawMinHint:'Мінімум виводу — 1 USDT. Кошти йдуть на поточну адресу профілю з розділу «Гаманець».'
    }
  };
  Object.entries(WALLET_IMPACT_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const BROADCAST_I18N = {
    ru:{
      broadcastPreview:'Предпросмотр',
      broadcastPreviewHint:'Так сообщение увидят в Telegram после очистки HTML.',
      broadcastPreviewEmpty:'Добавьте текст или картинку, чтобы увидеть предпросмотр.',
      broadcastTestSend:'Тест себе',
      broadcastTestHint:'Тест уходит только вам в Telegram и проверяет текст и форматирование. Картинка и кнопки в тесте не отправляются.',
      broadcastTestQueued:'Тестовое сообщение отправлено вам в Telegram',
      broadcastTestNeedsText:'Для теста нужен текст — картинка и кнопки не проверяются',
      broadcastLength:'Длина после очистки HTML: {length} из 4096',
      broadcastCaptionSplit:'Текст длиннее 1024 символов, поэтому Telegram пришлёт картинку и текст двумя сообщениями.',
      broadcastAudienceCount:'Получателей сейчас: {count} (заблокированные исключены)',
      broadcastAudienceUnknown:'Число получателей уточняется…',
      broadcastConfirmSend:'Отправить рассылку «{audience}» на {count} получателей?\n\nОтменить отправку после запуска нельзя.',
      broadcastNoRecipients:'В этой аудитории сейчас нет получателей',
      broadcastRetry:'Повторить неотправленные',
      broadcastRetryConfirm:'Повторить отправку для {count} получателей с ошибкой?\n\nТем, кто уже получил сообщение, оно повторно не уйдёт.',
      broadcastRetryQueued:'В очередь возвращено получателей: {count}',
      broadcastRetryNothing:'Нет неотправленных получателей',
      broadcastDelivered:'Доставлено',broadcastFailed:'Ошибки',broadcastPending:'В очереди',broadcastTotal:'Всего',
      broadcastNone:'Рассылок ещё не было.',
      audienceAll:'Все пользователи',audienceInvestors:'Только инвесторы',audiencePartners:'Только партнёры'
    },
    en:{
      broadcastPreview:'Preview',
      broadcastPreviewHint:'This is how Telegram renders the message after HTML sanitizing.',
      broadcastPreviewEmpty:'Add text or an image to see the preview.',
      broadcastTestSend:'Test to me',
      broadcastTestHint:'The test goes only to you in Telegram and checks text and formatting. Image and buttons are not sent in a test.',
      broadcastTestQueued:'Test message sent to you in Telegram',
      broadcastTestNeedsText:'A test needs text — image and buttons are not checked',
      broadcastLength:'Length after HTML sanitizing: {length} of 4096',
      broadcastCaptionSplit:'Text is longer than 1024 characters, so Telegram will send the image and the text as two messages.',
      broadcastAudienceCount:'Recipients right now: {count} (blocked users excluded)',
      broadcastAudienceUnknown:'Counting recipients…',
      broadcastConfirmSend:'Send the "{audience}" broadcast to {count} recipients?\n\nIt cannot be cancelled once started.',
      broadcastNoRecipients:'This audience has no recipients right now',
      broadcastRetry:'Retry undelivered',
      broadcastRetryConfirm:'Retry delivery for {count} failed recipients?\n\nAnyone who already received the message will not get it again.',
      broadcastRetryQueued:'Recipients requeued: {count}',
      broadcastRetryNothing:'No undelivered recipients',
      broadcastDelivered:'Delivered',broadcastFailed:'Failed',broadcastPending:'Queued',broadcastTotal:'Total',
      broadcastNone:'No broadcasts yet.',
      audienceAll:'All users',audienceInvestors:'Investors only',audiencePartners:'Partners only'
    },
    uk:{
      broadcastPreview:'Попередній перегляд',
      broadcastPreviewHint:'Так повідомлення побачать у Telegram після очищення HTML.',
      broadcastPreviewEmpty:'Додайте текст або картинку, щоб побачити перегляд.',
      broadcastTestSend:'Тест собі',
      broadcastTestHint:'Тест іде лише вам у Telegram і перевіряє текст та форматування. Картинка і кнопки в тесті не надсилаються.',
      broadcastTestQueued:'Тестове повідомлення надіслано вам у Telegram',
      broadcastTestNeedsText:'Для тесту потрібен текст — картинка і кнопки не перевіряються',
      broadcastLength:'Довжина після очищення HTML: {length} з 4096',
      broadcastCaptionSplit:'Текст довший за 1024 символи, тому Telegram надішле картинку і текст двома повідомленнями.',
      broadcastAudienceCount:'Отримувачів зараз: {count} (заблокованих виключено)',
      broadcastAudienceUnknown:'Рахуємо отримувачів…',
      broadcastConfirmSend:'Надіслати рассилку «{audience}» на {count} отримувачів?\n\nСкасувати після запуску неможливо.',
      broadcastNoRecipients:'У цій аудиторії зараз немає отримувачів',
      broadcastRetry:'Повторити невідправлені',
      broadcastRetryConfirm:'Повторити надсилання для {count} отримувачів з помилкою?\n\nТим, хто вже отримав повідомлення, воно повторно не піде.',
      broadcastRetryQueued:'У чергу повернуто отримувачів: {count}',
      broadcastRetryNothing:'Немає невідправлених отримувачів',
      broadcastDelivered:'Доставлено',broadcastFailed:'Помилки',broadcastPending:'У черзі',broadcastTotal:'Усього',
      broadcastNone:'Розсилок ще не було.',
      audienceAll:'Усі користувачі',audienceInvestors:'Лише інвестори',audiencePartners:'Лише партнери'
    }
  };
  Object.entries(BROADCAST_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const normalizeLanguage = (code) => {
    const raw = String(code || '').toLowerCase().replace('_','-').split('-')[0];
    return LANGS.some((x) => x[0] === raw) ? raw : 'ru';
  };
  const telegramLang = tg && tg.initDataUnsafe && tg.initDataUnsafe.user ? tg.initDataUnsafe.user.language_code : '';
  const NOVERA_SESSION_KEY = 'novera_auth_session_v10';
  // Hidden migration aliases keep existing Telegram sessions working while
  // every visible product surface remains NOVERA-only.
  const RETIRED_STORAGE_PREFIX = 'g' + 'fort';
  const COMPAT_HEADER_PREFIX = 'X-' + 'G' + 'FORT';
  const LEGACY_SESSION_KEY = `${RETIRED_STORAGE_PREFIX}_auth_session_v10`;
  const LEGACY_LANGUAGE_KEY = `${RETIRED_STORAGE_PREFIX}_lang`;
  const SESSION_STORAGE_KEYS = [NOVERA_SESSION_KEY, LEGACY_SESSION_KEY];
  Object.assign(I18N.ru, {
    accountMismatch: 'Сменился Telegram-аккаунт. Закройте Mini App и откройте NOVERA из бота под нужным аккаунтом.',
    loginLinkExpired: 'Ссылка входа устарела. Отправьте боту /start и откройте NOVERA из нового сообщения.',
  });
  Object.assign(I18N.en || (I18N.en = {}), {
    accountMismatch: 'Telegram account changed. Close the Mini App and open NOVERA again from the bot on the correct account.',
    loginLinkExpired: 'The login link expired. Send /start to the bot and open NOVERA from the new message.',
  });
  Object.assign(I18N.uk || (I18N.uk = {}), {
    accountMismatch: 'Змінився Telegram-акаунт. Закрийте Mini App і відкрийте NOVERA з бота під потрібним акаунтом.',
    loginLinkExpired: 'Посилання для входу застаріло. Надішліть боту /start і відкрийте NOVERA з нового повідомлення.',
  });
  const telegramPlatform = () => String(tg && tg.platform ? tg.platform : 'unknown').toLowerCase();
  const isNativeTelegramContext = () => Boolean(
    tg && telegramPlatform() !== 'unknown'
  ) || /(?:^|[&#])tgWebAppVersion=/.test(String(location.hash || ''));
  const launchInitDataFromHash = () => {
    try {
      const raw = String(location.hash || '').replace(/^#/, '');
      return raw ? String(new URLSearchParams(raw).get('tgWebAppData') || '') : '';
    } catch (_) { return ''; }
  };
  const readTelegramInitData = () => {
    // Telegram.WebApp.initData is the SDK's canonical current value. The URL
    // fragment may survive a reused WebView, so only use it as a fallback.
    const sdkData = tg ? String(tg.initData || '') : '';
    const hashData = launchInitDataFromHash();
    const looksSigned = (value) => value.includes('hash=') && value.includes('user=') && value.includes('auth_date=');
    if (sdkData && looksSigned(sdkData)) return sdkData;
    if (hashData && looksSigned(hashData)) return hashData;
    return '';
  };
  const signedTelegramUserId = (initData) => {
    try {
      const raw = new URLSearchParams(String(initData || '')).get('user');
      const value = raw ? Number(JSON.parse(raw).id) : 0;
      return Number.isSafeInteger(value) && value > 0 ? value : 0;
    } catch (_) { return 0; }
  };
  const unsafeTelegramUserId = () => {
    const value = tg && tg.initDataUnsafe && tg.initDataUnsafe.user ? Number(tg.initDataUnsafe.user.id) : 0;
    return Number.isSafeInteger(value) && value > 0 ? value : 0;
  };
  const sessionUserId = (token) => {
    try {
      const part = String(token || '').split('.', 1)[0];
      if (!part) return 0;
      const normalized = part.replace(/-/g, '+').replace(/_/g, '/');
      const padded = normalized + '='.repeat((4 - normalized.length % 4) % 4);
      const payload = JSON.parse(atob(padded));
      const value = Number(payload.uid || 0);
      return Number.isSafeInteger(value) && value > 0 ? value : 0;
    } catch (_) { return 0; }
  };
  const currentTelegramUserId = () => signedTelegramUserId(readTelegramInitData()) || unsafeTelegramUserId();

  const storageGet = (storage, key) => new Promise((resolve) => {
    if (!storage || typeof storage.getItem !== 'function') { resolve(''); return; }
    let settled=false;
    const finish=(value)=>{if(settled)return;settled=true;clearTimeout(timer);resolve(String(value||''));};
    const timer=setTimeout(()=>finish(''),900);
    try { storage.getItem(key,(err,value)=>finish(err ? '' : value)); } catch (_) { finish(''); }
  });
  const storageSet = (storage, key, value) => new Promise((resolve) => {
    if (!storage || typeof storage.setItem !== 'function') { resolve(false); return; }
    let settled=false;
    const finish=(ok)=>{if(settled)return;settled=true;clearTimeout(timer);resolve(Boolean(ok));};
    const timer=setTimeout(()=>finish(false),900);
    try { storage.setItem(key,String(value||''),(err,ok)=>finish(!err && ok !== false)); } catch (_) { finish(false); }
  });
  const storageRemove = (storage, key) => new Promise((resolve) => {
    if (!storage || typeof storage.removeItem !== 'function') { resolve(false); return; }
    let settled=false;
    const finish=(ok)=>{if(settled)return;settled=true;clearTimeout(timer);resolve(Boolean(ok));};
    const timer=setTimeout(()=>finish(false),900);
    try { storage.removeItem(key,(err,ok)=>finish(!err && ok !== false)); } catch (_) { finish(false); }
  });

  const state = {
    data:null, team:null, initData:readTelegramInitData(), telegramUserId:currentTelegramUserId(), loginToken:qs.get('login') || '',
    telegramSessionToken:'', telegramSessionLoaded:false,
    lang:normalizeLanguage(localStorage.getItem('novera_lang') || localStorage.getItem(LEGACY_LANGUAGE_KEY) || localStorage.getItem('delta_lang') || telegramLang),
    active:'home', historyFilter:'all', adminTab:qs.get('tab') || 'overview', adminUserTab:'overview', payoutFilter:'all', adminUserFilter:'all', adminCache:{}, refreshTimer:null,
    broadcastImageFile:null, broadcastImageUrl:'', broadcastButtons:[], broadcastAudience:null, accountRefreshBusy:false,
    notifications:[], notificationUnread:0, notificationFilter:'all', notificationLastId:0, notificationTimer:null,
    adminInvestmentOps:{},
    adminCloseInvestmentOps:{},
    activeInvoice:null,
    invoiceTimer:null,
    walletDirty:false,
    bootstrapInFlight:null
  };

  const loadTelegramSession = async (force=false) => {
    if (!isNativeTelegramContext()) {
      state.telegramSessionToken=''; state.telegramSessionLoaded=true; return '';
    }
    if (state.telegramSessionLoaded && !force) return state.telegramSessionToken;
    let token='';
    const storages=[];
    if (tg && tg.SecureStorage && (!tg.isVersionAtLeast || tg.isVersionAtLeast('9.0'))) storages.push(tg.SecureStorage);
    if (tg && tg.CloudStorage && (!tg.isVersionAtLeast || tg.isVersionAtLeast('6.9'))) storages.push(tg.CloudStorage);
    for (const storage of storages) {
      for (const key of SESSION_STORAGE_KEYS) {
        if (token) break;
        token=await storageGet(storage,key);
      }
      if (token) break;
    }
    // Migrate any compatible stored token into the NOVERA key.
    if (token && tg && tg.SecureStorage && (!tg.isVersionAtLeast || tg.isVersionAtLeast('9.0'))) {
      storageSet(tg.SecureStorage,NOVERA_SESSION_KEY,token).catch(()=>{});
    }
    const liveId=currentTelegramUserId();
    const tokenId=sessionUserId(token);
    if (token && tokenId && liveId && tokenId !== liveId) {
      // Signed initData belongs to another Telegram account than the stored
      // token — drop the stale token so we never bootstrap the wrong ledger.
      const tasks=[];
      for (const storage of storages) {
        for (const key of SESSION_STORAGE_KEYS) tasks.push(storageRemove(storage,key));
      }
      if (tasks.length) await Promise.allSettled(tasks);
      token='';
    }
    state.telegramSessionToken=token;
    state.telegramSessionLoaded=true;
    state.telegramUserId=sessionUserId(token) || liveId || currentTelegramUserId();
    return token;
  };
  const saveTelegramSession = async (token) => {
    const clean=String(token||'');
    if (!clean || !isNativeTelegramContext()) return false;
    state.telegramSessionToken=clean;
    state.telegramSessionLoaded=true;
    state.telegramUserId=sessionUserId(clean) || currentTelegramUserId();
    const tasks=[];
    if (tg && tg.SecureStorage && (!tg.isVersionAtLeast || tg.isVersionAtLeast('9.0'))) {
      for (const key of SESSION_STORAGE_KEYS) tasks.push(storageSet(tg.SecureStorage,key,clean));
    }
    if (tg && tg.CloudStorage && (!tg.isVersionAtLeast || tg.isVersionAtLeast('6.9'))) {
      for (const key of SESSION_STORAGE_KEYS) tasks.push(storageSet(tg.CloudStorage,key,clean));
    }
    if (tasks.length) await Promise.allSettled(tasks);
    return true;
  };
  const clearTelegramSession = async () => {
    state.telegramSessionToken=''; state.telegramSessionLoaded=true;
    const tasks=[];
    if (tg && tg.SecureStorage) {
      for (const key of SESSION_STORAGE_KEYS) tasks.push(storageRemove(tg.SecureStorage,key));
    }
    if (tg && tg.CloudStorage) {
      for (const key of SESSION_STORAGE_KEYS) tasks.push(storageRemove(tg.CloudStorage,key));
    }
    if (tasks.length) await Promise.allSettled(tasks);
  };
  const syncTelegramContext = () => {
    state.initData = readTelegramInitData();
    state.telegramUserId = sessionUserId(state.telegramSessionToken) || currentTelegramUserId();
    return state.initData;
  };
  const captureAuthSession = async (data) => {
    const token=String(data && data.auth_session_token ? data.auth_session_token : '');
    if (token) {
      await saveTelegramSession(token);
      try { delete data.auth_session_token; delete data.auth_session_expires_in; } catch (_) {}
    }
    return data;
  };
  const verifyBootstrapIdentity = (data) => {
    const expected = currentTelegramUserId() || sessionUserId(state.telegramSessionToken);
    const actual = Number(data && data.auth ? data.auth.telegram_id : 0);
    if (expected && actual && expected !== actual) {
      const error = new Error(tr('accountMismatch'));
      error.status = 409;
      error.detail = 'Telegram account context mismatch';
      throw error;
    }
    return data;
  };


  const tr = (key) => (I18N[state.lang] && I18N[state.lang][key]) || (state.lang === 'ru' ? I18N.ru[key] : I18N.en[key]) || I18N.ru[key] || key;
  const toast = (text, type='info') => { const el=$('toast'); el.textContent=text; el.className=`toast ${type} show`; clearTimeout(toast._t); toast._t=setTimeout(()=>{el.className='toast';},2800); };
  const statusText = (value) => {
    const keyMap = {
      active:'statusActive',completed:'statusCompleted',paused:'statusPaused',failed:'statusFailed',
      pending:'statusPending',paid:'statusPaid',expired:'statusExpired',confirmed:'statusConfirmed',
      queued:'statusQueued',signed:'statusSigned',broadcast:'statusBroadcast',sending:'statusSending'
    };
    const key = keyMap[value];
    return key ? tr(key) : (value || tr('none'));
  };
  const historyStatusMeta = (status) => {
    const s = String(status || '');
    if (s === 'failed' || s === 'expired') {
      return {tone:'needs-action', label:tr('historyNeedsAction'), hint:s==='failed'?tr('historyHintFailed'):tr('historyHintExpired')};
    }
    if (s === 'confirmed' || s === 'completed' || s === 'paid') {
      return {tone:'done', label:tr('historyDone'), hint:s==='confirmed'?tr('historyHintConfirmed'):tr('historyHintCompleted')};
    }
    const hints = {
      queued:tr('historyHintQueued'), signed:tr('historyHintSigned'), broadcast:tr('historyHintBroadcast'),
      active:tr('historyHintActive'), paused:tr('historyHintPaused'), pending:tr('historyHintPending')
    };
    return {tone:'waiting', label:tr('historyNoAction'), hint:hints[s] || tr('historyHintDefault')};
  };
  const ageLabel = (ts) => {
    const seconds = Math.max(0, Math.floor(Date.now()/1000) - Number(ts || 0));
    if (!Number.isFinite(seconds) || !ts) return '';
    if (seconds < 60) return tr('adminAgeSeconds').replace('{sec}', String(seconds));
    if (seconds < 3600) {
      const mins = Math.floor(seconds / 60);
      return tr('adminAgeMinutes').replace('{min}', String(mins));
    }
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (mins <= 0) return tr('adminAgeHours').replace('{hours}', String(hours));
    return tr('adminAgeHoursMinutes').replace('{hours}', String(hours)).replace('{min}', String(mins));
  };
  const openPayoutCounts = (payouts=[]) => {
    const counts={queued:0,signed:0,broadcast:0};
    (payouts||[]).forEach((p)=>{
      const status=String(p&&p.status||'');
      if(status==='queued') counts.queued+=1;
      else if(status==='signed') counts.signed+=1;
      else if(status==='broadcast') counts.broadcast+=1;
    });
    return counts;
  };
  const formatPipelineSummary = (counts) => {
    const total=counts.queued+counts.signed+counts.broadcast;
    if(!total) return tr('walletPipelineNone');
    return tr('walletPipelineOpen')
      .replace('{queued}',String(counts.queued))
      .replace('{signed}',String(counts.signed))
      .replace('{broadcast}',String(counts.broadcast));
  };
  const renderWalletImpact = (data) => {
    const summary=$('walletPipelineSummary');
    if(!summary) return;
    const counts=openPayoutCounts((data&&data.payouts)||[]);
    summary.textContent=formatPipelineSummary(counts);
  };
  const apiErrorText = (detail, status=0) => {
    const d=String(detail || '');
    const low=d.toLowerCase();
    if (low.includes('bot login link is invalid or expired')) return tr('loginLinkExpired');
    if (low.includes('account context mismatch') || low.includes('belongs to another telegram account')) return tr('accountMismatch');
    if (low.includes('initdata has expired') || low.includes('session has expired')) return tr('sessionExpired');
    if (low.includes('initdata is missing') || low.includes('session is missing') || low.includes('authorization is unavailable')) return tr('openFromTelegram');
    if (low.includes('account is blocked')) return tr('accountBlocked');
    if (low.includes('admin access required')) return tr('adminAccessRequired');
    if (low.includes('owner access required')) return tr('ownerRequired');
    if (low.includes('fresh telegram authorization')) return tr('reopenForFreshAuth');
    if (low.includes('financial services are locked')) return tr('financialLocked');
    if (low.includes('user not found')) return tr('userNotFound');
    if (low.includes('invalid administrator identifier')) return tr('invalidAdmin');
    if (low.includes('administrator cannot remove itself')) return tr('cannotRemoveSelf');
    if (low.includes('bootstrap administrator cannot be removed')) return tr('cannotRemoveOwner');
    if (low.includes('administrator grant not found')) return tr('adminGrantNotFound');
    if (low.includes('invalid bnb chain address')) return tr('invalidWallet');
    if (low.includes('deposits are temporarily disabled')) return tr('depositsDisabled');
    if (low.includes('treasury wallet is not configured')) return tr('treasuryNotConfigured');
    if (low.includes('payout period cannot be below')) return tr('settingsPayoutDaysConflict');
    if (low.includes('button url')) return tr('invalidButton');
    if (low.includes('broadcast message or image')) return tr('broadcastRequiresContent');
    if (low.includes('blockchain configuration failed health check')) return tr('chainHealthFailed');
    if (low.includes('seed phrase')) return tr('seedInvalid');
    if (low.includes('token contract')) return tr('invalidContract');
    if (low.includes('set a payout wallet before withdrawing referral rewards') || low.includes('set a payout wallet before creating a deposit')) return tr('setPayoutWalletFirst');
    if (low.includes('too many pending deposit invoices')) return tr('tooManyPendingInvoices');
    if (low.includes('promo code already redeemed by this user')) return tr('promoAlreadyRedeemed');
    if (low.includes('deposit amount is below promo minimum')) return tr('promoMinDepositError');
    if (low.includes('promo code is not available') || low.includes('promo code is not yet active') || low.includes('promo code has expired') || low.includes('promo code redemption limit reached') || low.includes('promo code does not grant a bonus') || low.includes('promo would exceed deposit maximum') || low.includes('promo code not found')) return tr('promoInvalid');
    if (low.includes('user payout wallet is not configured')) return tr('userWalletRequired');
    if (low.includes('referral balance below minimum withdrawal')) return tr('referralMinimum');
    if (low.includes('referrer not found')) return tr('referrerNotFound');
    if (low.includes('referral cycle')) return tr('referrerCycle');
    if (low.includes('own referrer')) return tr('referrerSelf');
    if (low.includes('ambiguous')) return tr('ambiguousReferrer');
    if (low.includes('payouts are temporarily disabled')) return tr('payoutsDisabled');
    if (low.includes('real payouts are not enabled')) return tr('realPayoutsDisabled');
    if (low.includes('insufficient treasury usdt balance')) return tr('treasuryInsufficientUsdt');
    if (low.includes('treasury has no bnb for gas')) return tr('treasuryNoGas');
    if (low.includes('destination must differ from treasury')) return tr('testPayoutSameWallet');
    if (low.includes('minimum admin test payout')) return tr('testPayoutMinimum');
    if (status===429 || low.includes('too many requests')) return tr('tooManyRequests');
    if (status===413 || low.includes('request body is too large')) return tr('requestTooLarge');
    if (low.includes('production mode requires a positive scan start block')) return tr('scanBlockRequired');
    if (low.includes('treasury confirmation does not match')) return tr('treasuryConfirmMismatch');
    if (low.includes('health check')) return tr('chainHealthFailed');
    if (low.includes('dns lookup failed')) return tr('chainDnsFailed');
    if (low.includes('seed phrase must contain') || low.includes('cannot derive an evm wallet')) return tr('secretFieldsRequired');
    if (status===422) return d || tr('invalidData');
    if (status===409) return tr('accountMismatch');
    if (status===401) return tr('sessionExpired');
    return tr('requestFailed');
  };

  if (tg) {
    tg.ready(); tg.expand();
    try { tg.setHeaderColor('#00050A'); tg.setBackgroundColor('#00050A'); } catch (_) {}
    const syncHeight = () => document.documentElement.style.setProperty('--tg-height', `${tg.viewportStableHeight || window.innerHeight}px`);
    syncHeight(); if (tg.onEvent) tg.onEvent('viewportChanged', syncHeight);
  }

  async function api(path, options={}) {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      setOfflineBanner(true);
      const err=new Error(tr('networkError'));
      err.status=0; err.detail='offline';
      throw err;
    }
    const headers = new Headers(options.headers || {});
    const initData = syncTelegramContext();
    // Send the canonical header plus a hidden rollback-compatible alias.
    if (state.telegramSessionToken) {
      headers.set('X-NOVERA-Session', state.telegramSessionToken);
      headers.set(`${COMPAT_HEADER_PREFIX}-Session`, state.telegramSessionToken);
    } else {
      headers.delete('X-NOVERA-Session');
      headers.delete(`${COMPAT_HEADER_PREFIX}-Session`);
    }
    if (initData) headers.set('X-Telegram-Init-Data', initData);
    else headers.delete('X-Telegram-Init-Data');
    if (isNativeTelegramContext()) {
      headers.set('X-NOVERA-Telegram-Context', '1');
      headers.set(`${COMPAT_HEADER_PREFIX}-Telegram-Context`, '1');
    }
    headers.set('X-Request-Id', (crypto.randomUUID ? crypto.randomUUID() : `req-${Date.now()}-${Math.random()}`).replace(/-/g,''));
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type','application/json');
    const controller = options.signal ? null : new AbortController();
    const timeoutMs = Number(options.timeoutMs || 20000);
    const slowTimer = setTimeout(()=>{ if($('networkStatus')){ $('networkStatus').textContent=tr('slowNetwork'); $('networkStatus').classList.remove('hidden'); } }, Math.min(8000, timeoutMs));
    const timer = controller ? setTimeout(()=>controller.abort(), timeoutMs) : null;
    try{
      const res = await fetch(path, {...options, headers, credentials:'same-origin', signal: options.signal || (controller && controller.signal)});
      clearTimeout(slowTimer); if(timer) clearTimeout(timer);
      setOfflineBanner(false);
      let body=null; try{body=await res.json();}catch(_){body=null;}
      if (!res.ok) {
        const err=new Error(apiErrorText(body && body.detail ? body.detail : '', res.status));
        err.status=res.status; err.detail=body && body.detail ? body.detail : '';
        throw err;
      }
      return body;
    }catch(e){
      clearTimeout(slowTimer); if(timer) clearTimeout(timer);
      if (e && (e.name === 'AbortError' || e.message === 'The user aborted a request.')) {
        const err=new Error(tr('requestTimeout'));
        err.status=0; err.detail='timeout';
        throw err;
      }
      if (e && e.status !== undefined) throw e;
      setOfflineBanner(true);
      const err=new Error(tr('networkError'));
      err.status=0; err.detail=String(e&&e.message||'network');
      throw err;
    }
  }

  function setOfflineBanner(offline){
    const banner=$('offlineBanner');
    if(!banner) return;
    banner.classList.toggle('hidden', !offline);
    if(offline){
      const title=banner.querySelector('[data-offline-title]');
      const text=banner.querySelector('[data-offline-text]');
      if(title) title.textContent=tr('offlineTitle');
      if(text) text.textContent=tr('offlineText');
      if($('retryConnection')) $('retryConnection').textContent=tr('retryConnection');
    } else if($('networkStatus')) {
      $('networkStatus').classList.add('hidden');
      $('networkStatus').textContent='';
    }
  }


  async function exchangeBotLogin() {
    if (!state.loginToken) return false;
    const token = state.loginToken;
    const headers = new Headers({
      'Content-Type':'application/json',
      'X-Request-Id':(crypto.randomUUID ? crypto.randomUUID() : `req-${Date.now()}-login`).replace(/-/g,'')
    });
    const initData = syncTelegramContext();
    if (state.telegramSessionToken) {
      headers.set('X-NOVERA-Session', state.telegramSessionToken);
      headers.set(`${COMPAT_HEADER_PREFIX}-Session`, state.telegramSessionToken);
    }
    if (initData) headers.set('X-Telegram-Init-Data', initData);
    if (isNativeTelegramContext()) {
      headers.set('X-NOVERA-Telegram-Context', '1');
      headers.set(`${COMPAT_HEADER_PREFIX}-Telegram-Context`, '1');
    }
    const clearToken = () => {
      state.loginToken='';
      const url=new URL(window.location.href);
      url.searchParams.delete('login');
      history.replaceState(null,'',`${url.pathname}${url.search}${url.hash}`);
    };
    try {
      const res = await fetch('/api/session/exchange', {
        method:'POST', headers, body:JSON.stringify({token}),
        credentials:'same-origin', cache:'no-store'
      });
      let body=null; try{body=await res.json();}catch(_){body=null;}
      if (!res.ok) {
        if ([401,409,422].includes(res.status)) clearToken();
        return false;
      }
      if (body && body.session_token) await saveTelegramSession(body.session_token);
      clearToken();
      return true;
    } catch (_) { return false; }
  }


  function applyTranslations() {
    document.documentElement.lang=state.lang;
    document.querySelectorAll('[data-i18n]').forEach((el)=>{ const key=el.dataset.i18n; const value=tr(key); if(value) el.textContent=value; });
    const lang=LANGS.find((x)=>x[0]===state.lang) || LANGS[0]; $('languageShort').textContent=lang[1];
    renderLanguageList();
    if (state.data) render(state.data, {preserve:true});
    if (state.team) renderTeam(state.team);
    renderBroadcastPreview();
    renderBroadcastAudienceCount();
    if (state.active==='admin' && state.data && state.data.auth && state.data.auth.is_admin) loadAdminTab(state.adminTab);
  }

  function renderLanguageList() {
    $('languageList').innerHTML=LANGS.map(([code,short,name,native])=>`<button class="language-option ${code===state.lang?'active':''}" type="button" data-language="${code}"><span><strong>${esc(native)}</strong><small>${esc(name)} · ${esc(short)}</small></span><span class="language-check">${code===state.lang?'✓':''}</span></button>`).join('');
    $('languageList').querySelectorAll('[data-language]').forEach((b)=>b.addEventListener('click',()=>setLanguage(b.dataset.language)));
  }
  function setLanguage(code){ state.lang=normalizeLanguage(code); localStorage.setItem('novera_lang',state.lang); $('languageSheet').classList.add('hidden'); applyTranslations(); }
  function showLanguage(){ $('languageSheet').classList.remove('hidden'); renderLanguageList(); }

  function switchView(name, {push=false}={}) {
    state.active=name;
    document.querySelectorAll('.view').forEach((v)=>v.classList.toggle('active',v.id===`view-${name}`));
    document.querySelectorAll('.nav-btn').forEach((b)=>{
      const on=b.dataset.view===name;
      b.classList.toggle('active',on);
      if(on) b.setAttribute('aria-current','page'); else b.removeAttribute('aria-current');
    });
    if (push) history.replaceState(null,'',`${location.pathname}?view=${encodeURIComponent(name)}${name==='admin'?`&tab=${encodeURIComponent(state.adminTab)}`:''}`);
    window.scrollTo({top:0,behavior:'auto'});
    if(name==='team') loadTeam();
    if(name==='notifications') loadNotifications();
    if(name==='admin') loadAdmin(state.adminTab);
  }

  function render(data, {preserve=false}={}) {
    state.data=data;
    const auth=data.auth||{}, user=data.user||{}, team=data.team||{}, terms=data.terms||{}, chain=data.chain||{};
    const deposits=data.deposits||[], payouts=data.payouts||[];
    const active=deposits.filter((x)=>x.status==='active');
    const activeMinor=active.reduce((s,x)=>s+Number(x.principal_minor||0),0);
    const depositedMinor=deposits.reduce((s,x)=>s+Number(x.principal_minor||0),0);
    const paidMinor=payouts.filter((x)=>x.status==='confirmed').reduce((s,x)=>s+Number(x.amount_minor||0),0);
    const expectedMinor=projectedRemainingMinor(deposits, terms);
    const nextInfo=nextPayoutInfo(deposits, terms);
    const name=auth.first_name||user.first_name||'NOVERA';
    state.notificationUnread=Number(data.notification_unread_count||state.notificationUnread||0);
    updateNotificationBadge();

    $('accountState').textContent=tr('online');
    $('networkState').textContent=chain.enabled ? `BSC ${chain.chain_id||''} · ${chain.token_symbol||'USDT'}` : 'WEB';
    $('heroName').textContent=name; $('heroName').classList.toggle('long-name',Array.from(String(name)).length>12);
    $('activePrincipal').textContent=money(activeMinor);
    if (nextInfo) {
      const principalNote = nextInfo.includes_principal ? ` · ${tr('nextPayoutWithPrincipal')}` : '';
      $('nextPayoutValue').textContent=`${fmtShort(nextInfo.at)} · ${money(nextInfo.amount_minor)} USDT${principalNote}`;
    } else {
      $('nextPayoutValue').textContent=tr('nextPayoutNone');
    }
    if ($('homePaid')) $('homePaid').textContent=money(paidMinor);
    if ($('homeExpected')) $('homeExpected').textContent=money(expectedMinor);
    if ($('homePartnerAvailable')) $('homePartnerAvailable').textContent=money(team.referral_available_minor);
    if ($('accountBalance')) $('accountBalance').textContent=money(user.manual_balance_minor);
    $('totalDeposited').textContent=money(depositedMinor);
    if ($('totalPaid')) $('totalPaid').textContent=money(paidMinor);
    $('teamCount').textContent=team.count||0;
    if ($('refIncome')) $('refIncome').textContent=money(team.referral_earned_minor);
    $('termMin').textContent=`${terms.deposit_min_usdt||0} USDT`;
    $('termDays').textContent=`${terms.payout_days||0} ${tr('days')}`;
    $('termRate').textContent=percent(terms.daily_profit_bps);
    $('termsHeadline').textContent=`${percent(terms.daily_profit_bps)} · ${terms.payout_days||0} ${tr('days')}`;
    renderProfitCalculator(terms);
    const walletEl=$('walletInput');
    if(walletEl && !(state.walletDirty || document.activeElement===walletEl)){
      walletEl.value=user.payout_address||'';
    }
    $('walletState').textContent=user.payout_address ? compactAddress(user.payout_address) : '';
    renderWalletImpact(data);
    updateDepositForm(data);
    if(state.activeInvoice) renderInvoice(state.activeInvoice);
    $('referralLink').textContent=data.referral_link||'—';

    $('profileName').textContent=name;
    $('profileUsername').textContent=auth.username?`@${auth.username}`:`ID ${auth.telegram_id||user.telegram_id||'—'}`;
    $('profileAvatar').textContent=(name[0]||'N').toUpperCase(); $('profileBtn').textContent=(name[0]||'N').toUpperCase();
    $('profileRole').textContent=auth.is_admin?tr('adminRole'):tr('userRole');
    const ref=data.referrer||null;
    const inviter=ref?(ref.username?`@${ref.username}`:(ref.first_name||`ID ${ref.telegram_id}`)):tr('none');
    $('profileDetails').innerHTML=[
      [tr('telegramId'),auth.telegram_id||user.telegram_id||'—'],[tr('role'),auth.is_admin?tr('adminRole'):tr('userRole')],
      [tr('registered'),fmtDate(user.created_at)],[tr('inviter'),inviter],[tr('team'),team.count||0],[tr('accountBalance'),`${money(user.manual_balance_minor)} USDT`],[tr('payoutAddress'),user.payout_address||tr('none')]
    ].map(([k,v])=>`<div class="detail-row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');

    if(auth.is_admin) $('adminNav').classList.remove('hidden'); else $('adminNav').classList.add('hidden');
    renderAssets(deposits,terms); renderHistory(deposits,payouts,chain); renderLevelCards(data);
    if(!preserve){
      const requested=qs.get('view');
      if(requested==='admin'&&auth.is_admin) switchView('admin');
      else if(['home','assets','wallet','team','history','profile'].includes(requested)) switchView(requested);
    }
  }

  function renderProfitCalculator(terms=(state.data&&state.data.terms)||{}){
    const input=$('profitCalcAmount');
    if(!input)return;
    const min=Math.max(0,Number(terms.deposit_min_usdt||0));
    const max=Math.max(min,Number(terms.deposit_max_usdt||0));
    input.min=String(min||1); if(max)input.max=String(max);
    if(!input.value){
      const fallback=Math.max(min,Math.min(max||100,100));
      input.value=String(fallback||min||100);
    }
    $('profitCalcRange').textContent=`${tr('depositRange')}: ${calcMoney(min)}–${calcMoney(max)} USDT`;
    updateProfitCalculator();
  }
  function updateProfitCalculator(){
    const input=$('profitCalcAmount'), terms=(state.data&&state.data.terms)||{};
    if(!input)return;
    const amount=Number(input.value), min=Number(terms.deposit_min_usdt||0), max=Number(terms.deposit_max_usdt||0);
    const bps=Number(terms.daily_profit_bps||0), days=Math.max(0,Number(terms.payout_days||0));
    const valid=Number.isFinite(amount)&&amount>0&&amount>=min&&(!max||amount<=max)&&bps>=0&&days>0;
    const ids=['calcDailyProfit','calcTermProfit','calcPrincipalReturn','calcTotalReturn','calcFinalDay'];
    if(!valid){ids.forEach((id)=>{if($(id))$(id).textContent='—';});if($('calculatorToDeposit'))$('calculatorToDeposit').disabled=true;return;}
    const daily=amount*(bps/10000), term=daily*days, total=amount+term, finalDay=amount+daily;
    $('calcDailyProfit').textContent=calcMoney(daily);
    $('calcTermProfit').textContent=calcMoney(term);
    $('calcPrincipalReturn').textContent=calcMoney(amount);
    $('calcTotalReturn').textContent=calcMoney(total);
    $('calcFinalDay').textContent=calcMoney(finalDay);
    $('calculatorToDeposit').disabled=false;
  }
  function calculatorToDeposit(){
    const amount=Number($('profitCalcAmount').value), terms=(state.data&&state.data.terms)||{};
    if(!Number.isFinite(amount)||amount<Number(terms.deposit_min_usdt||0)||amount>Number(terms.deposit_max_usdt||Infinity)){updateProfitCalculator();return;}
    $('depositAmount').value=String(amount);
    switchView('wallet',{push:true});
  }

  function renderAssets(deposits, terms) {
    const active=deposits.filter((x)=>x.status==='active'), completed=deposits.filter((x)=>x.status==='completed');
    const activeMinor=active.reduce((s,x)=>s+Number(x.principal_minor||0),0);
    const expectedMinor=projectedRemainingMinor(deposits, terms);
    $('assetsSummary').innerHTML=[
      [tr('activeCount'),active.length],
      [tr('activeAssets'),`${money(activeMinor)} USDT`],
      [tr('expectedRemaining'),`${money(expectedMinor)} USDT`],
      [tr('completedCount'),completed.length]
    ].map(([k,v])=>`<div class="summary-mini"><span>${esc(k)}</span><strong class="money">${esc(v)}</strong></div>`).join('');
    const totalDays=Math.max(1,Number(terms.payout_days||20));
    $('assetList').innerHTML=deposits.length?deposits.map((d)=>{
      const paidDays=Number(d.paid_days||0);
      const scheduled=Number(d.scheduled_days||0);
      const progress=Math.max(0,Math.min(100,(paidDays/totalDays)*100));
      const paid=depositPaidMinor(d, terms);
      const remaining=depositRemainingMinor(d, terms);
      const day=Math.min(totalDays, scheduled + 1);
      const daily=bpsMinor(d.principal_minor, terms.daily_profit_bps);
      let nextAmount=daily;
      const includesPrincipal=d.status==='active' && day>=totalDays;
      if (includesPrincipal) nextAmount += Number(d.principal_minor||0);
      const nextLine=d.status==='active'
        ? `${esc(tr('assetNextPayment'))}: ${esc(fmtShort(d.next_payout_at))} · ${esc(money(nextAmount))} USDT${includesPrincipal?` · ${esc(tr('assetIncludesPrincipal'))}`:''}`
        : `${esc(tr('assetPaid'))}: ${esc(money(paid))} USDT`;
      const scheduleAddress=d.payout_address?`<small class="asset-payout-address">${esc(tr('depositPayoutAddressLabel'))}: ${esc(compactAddress(d.payout_address))}</small>`:'';
      return `<article class="list-card asset-card"><div class="list-card-header"><div><strong class="money">${money(d.principal_minor)} USDT</strong><small>#${esc(d.id)} · ${fmtDate(d.opened_at)}</small></div><span class="tag ${esc(d.status)}">${esc(statusText(d.status))}</span></div><div class="asset-money-rows"><div><span>${esc(tr('assetPaid'))}</span><strong class="money amount-positive">${esc(money(paid))} USDT</strong></div><div><span>${esc(tr('assetRemaining'))}</span><strong class="money">${esc(money(remaining))} USDT</strong></div></div><progress class="asset-progress" max="100" value="${progress.toFixed(1)}"></progress><small>${esc(tr('progress'))}: ${paidDays}/${totalDays} ${esc(tr('days'))}</small><small class="asset-next">${nextLine}</small>${scheduleAddress}</article>`;
    }).join(''):`<div class="empty-state">${esc(tr('noAssets'))}</div>`;
  }

  function renderHistory(deposits,payouts,chain) {
    const events=[];
    deposits.forEach((x)=>events.push({type:'deposits',title:tr('deposit'),status:x.status,amount:money(x.principal_minor),ts:x.opened_at,id:x.id,address:x.payout_address||'',error:x.last_error||x.fail_reason||''}));
    payouts.forEach((x)=>events.push({type:'payouts',title:x.subtype==='principal'?tr('principalReturn'):(x.kind==='referral'?tr('referral'):tr('daily')),status:x.status,amount:money(x.amount_minor),ts:x.created_at,id:x.id,tx:x.tx_hash,address:x.address||'',error:x.last_error||''}));
    events.sort((a,b)=>Number(b.ts)-Number(a.ts));
    const filtered=state.historyFilter==='all'?events:events.filter((x)=>x.type===state.historyFilter);
    $('historyList').innerHTML=filtered.length?filtered.map((e)=>{
      const meta=historyStatusMeta(e.status);
      const payoutConfirmed=e.type==='payouts' && String(e.status)==='confirmed';
      const amountClass=payoutConfirmed?'amount-positive':(e.type==='payouts' && (e.status==='failed'||e.status==='expired')?'amount-negative':'');
      const amountPrefix=e.type==='payouts'?(payoutConfirmed?'+':''):'';
      const addressLine=e.address?`<small class="history-payout-meta">${esc(e.type==='payouts'?tr('payoutAddressLabel'):tr('depositPayoutAddressLabel'))}: ${esc(compactAddress(e.address))}</small>`:'';
      const actionLine=`<div class="history-status-row ${esc(meta.tone)}"><span class="history-status-pill">${esc(meta.label)}</span><small>${esc(meta.hint)}${e.error?' · '+esc(e.error):''}</small></div>`;
      return `<article class="list-card history-card"><div class="list-card-header"><div><strong>${esc(e.title)}</strong><small>#${esc(e.id)} · ${esc(fmtDate(e.ts))}</small></div><div><strong class="${amountClass}">${amountPrefix}${esc(e.amount)} USDT</strong><small class="status-text ${esc(e.status)}">${esc(statusText(e.status))}</small></div></div>${addressLine}${actionLine}${e.tx&&chain.explorer_tx_url?`<a class="tx-link" href="${esc(chain.explorer_tx_url.replace('{tx_hash}',e.tx))}" target="_blank" rel="noopener">${esc(compactAddress(e.tx))}</a>`:''}</article>`;
    }).join(''):`<div class="empty-state">${esc(tr('noHistory'))}</div>`;
  }

  function renderLevelCards(data){
    const terms=data.terms||{}, rates=terms.referral_level_bps||[], personal=terms.referral_personal_thresholds_usdt||[], line=terms.referral_line_thresholds_usdt||[];
    const teamLevels=state.team&&state.team.levels?state.team.levels:[];
    $('levelCards').innerHTML=rates.map((rate,i)=>{const s=teamLevels.find((x)=>Number(x.level)===i+1)||{};return `<article class="level-card"><div class="level-card-top"><span class="level-badge">${i+1}</span><span class="level-rate">${percent(rate)}</span></div><dl><div><dt>${esc(tr('members'))}</dt><dd>${esc(s.member_count||0)}</dd></div><div><dt>${esc(tr('turnover'))}</dt><dd>${money(s.deposited_minor)} USDT</dd></div><div><dt>${esc(tr('earned'))}</dt><dd>${money(s.earned_minor)} USDT</dd></div><div><dt>${esc(tr('personal'))}</dt><dd>${esc(personal[i]||0)} USDT</dd></div><div><dt>${esc(tr('line'))}</dt><dd>${esc(line[i]||0)} USDT</dd></div></dl></article>`;}).join('');
  }

  function updateNotificationBadge(){
    const badge=$('notificationBadge'); if(!badge)return;
    const count=Math.max(0,Number(state.notificationUnread||0));
    badge.textContent=count>99?'99+':String(count);
    badge.classList.toggle('hidden',count<=0);
    $('notificationsBtn').classList.toggle('has-unread',count>0);
  }
  function notificationIcon(category,eventType){
    if(category==='deposit')return '↧';
    if(category==='payout')return String(eventType||'').includes('failed')?'!':'↗';
    if(category==='partner')return '◎';
    return '•';
  }
  function renderNotifications(payload){
    const items=Array.isArray(payload&&payload.items)?payload.items:[];
    state.notifications=items; state.notificationUnread=Number(payload&&payload.unread_count||0);
    updateNotificationBadge();
    const filtered=state.notificationFilter==='all'?items:items.filter((n)=>n.category===state.notificationFilter);
    const unread=filtered.filter((n)=>!n.read_at).length;
    const heading=unread?`<p class="notification-unread-hint">${esc(tr('unreadNotifications'))}: ${esc(unread)}</p>`:'';
    $('notificationList').innerHTML=heading+(filtered.length?filtered.map((n)=>`<article class="list-card notification-card ${n.read_at?'':'unread'}" data-notification-id="${esc(n.id)}"><div class="notification-icon ${esc(n.category||'system')}">${esc(notificationIcon(n.category,n.event_type))}</div><div class="notification-copy"><div class="list-card-header"><strong>${esc(n.title||tr('notifications'))}</strong><span class="date-text">${esc(fmtDate(n.created_at))}</span></div><p>${esc(n.body||'')}</p><small class="notification-cat">${esc(({deposit:tr('notificationCatDeposit'),payout:tr('notificationCatPayout'),partner:tr('notificationCatPartner'),system:tr('notificationCatSystem')})[n.category]||tr('notificationCatSystem'))}</small></div></article>`).join(''):`<div class="empty-state">${esc(tr('noNotifications'))}</div>`);
    $('notificationList').querySelectorAll('[data-notification-id]').forEach((card)=>card.addEventListener('click',async()=>{
      const id=Number(card.dataset.notificationId); const item=state.notifications.find((x)=>Number(x.id)===id);
      if(item&&!item.read_at){try{await api(`/api/notifications/${id}/read`,{method:'POST'});item.read_at=Math.floor(Date.now()/1000);state.notificationUnread=Math.max(0,state.notificationUnread-1);updateNotificationBadge();card.classList.remove('unread');}catch(e){handleApiError(e);return;}}
      const target=item&&item.data&&item.data.target_view; if(target&&document.getElementById(`view-${target}`))switchView(target,{push:true});
    }));
  }
  async function loadNotifications({silent=false}={}){
    if(document.visibilityState==='hidden'&&silent)return;
    try{
      const payload=await api('/api/notifications?limit=100',{cache:'no-store'});
      const items=Array.isArray(payload.items)?payload.items:[];
      const maxId=items.reduce((m,n)=>Math.max(m,Number(n.id||0)),0);
      if(silent&&state.notificationLastId&&maxId>state.notificationLastId){
        const newest=items.find((n)=>Number(n.id)===maxId); if(newest)toast(`${tr('newNotification')}: ${newest.title}`,'info');
      }
      state.notificationLastId=Math.max(state.notificationLastId,maxId);
      renderNotifications(payload);
    }catch(e){
      if(!silent&&e.status!==401){
        if($('notificationList')) $('notificationList').innerHTML=`<div class="empty-state error-state">${esc(tr('notificationsLoadError'))}</div>`;
        handleApiError(e);
      }
    }
  }
  async function markAllNotificationsRead(){
    try{await api('/api/notifications/read-all',{method:'POST'});await loadNotifications();}catch(e){handleApiError(e);}
  }

  async function loadTeam(){
    if(!state.data)return;
    const now=new Date();
    const todayStart=Math.floor(new Date(now.getFullYear(),now.getMonth(),now.getDate()).getTime()/1000);
    try{ state.team=await api(`/api/team?today_start=${todayStart}`); renderTeam(state.team); renderLevelCards(state.data); }catch(e){ if(e.status!==401)handleApiError(e); }
  }
  function renderTeam(team){
    const ref=team.referrer||null;
    const inviter=ref?(ref.username?`@${ref.username}`:(ref.first_name||`ID ${ref.telegram_id}`)):tr('none');
    if($('teamInviter')) $('teamInviter').innerHTML=`<span>${esc(tr('inviter'))}</span><strong>${esc(inviter)}</strong>`;
    const stats=team.stats||{};
    if($('teamReferralIncome')) $('teamReferralIncome').textContent=money(stats.earned_minor);
    if($('teamTodayIncome')) $('teamTodayIncome').textContent=money(stats.today_minor);
    if($('teamPersonal')) $('teamPersonal').textContent=money(stats.personal_minor);
    if($('teamLineTurnover')) $('teamLineTurnover').textContent=money(stats.line_minor);
    if($('teamTotalMembers')) $('teamTotalMembers').textContent=Number(stats.team_count||0);
    if($('teamCurrentLevel')) $('teamCurrentLevel').textContent=Number(stats.current_level||0);
    if($('teamLevelsTotal')) $('teamLevelsTotal').textContent=Number(stats.levels_total||5);
    if($('referralAvailable')) $('referralAvailable').textContent=money(stats.available_minor);
    if($('referralPending')) $('referralPending').textContent=money(stats.pending_minor);
    const failedMinor=Number(stats.failed_minor||0);
    if($('referralFailedWrap')){
      $('referralFailedWrap').classList.toggle('hidden', failedMinor<=0);
      if($('referralFailed')) $('referralFailed').textContent=money(failedMinor);
    }
    if($('teamLevelSource')){
      const manual=Number(stats.manual_level||0)>0;
      $('teamLevelSource').textContent=manual?tr('levelSourceManual'):tr('levelSourceAuto');
      $('teamLevelSource').classList.toggle('manual', manual);
    }
    if($('availablePendingHint')) $('availablePendingHint').textContent=tr('availableVsPending');
    const minWithdrawal=Number(stats.minimum_withdrawal_minor||1000000);
    const available=Number(stats.available_minor||0);
    const payoutsOn=Boolean(state.data&&state.data.chain&&state.data.chain.payouts_enabled);
    const financialReady=Boolean(
      (state.data&&state.data.setup&&state.data.setup.financial_ready) ||
      (state.data&&state.data.mode&&state.data.mode.setup&&state.data.mode.setup.financial_ready)
    );
    const hasWallet=Boolean(stats.payout_address||(state.data&&state.data.user&&state.data.user.payout_address));
    let withdrawHint=tr('withdrawMinHint');
    let withdrawDisabled=true;
    if(!financialReady){ withdrawHint=tr('withdrawDisabledBootstrap'); }
    else if(!payoutsOn){ withdrawHint=tr('withdrawDisabledPayouts'); }
    else if(!hasWallet){ withdrawHint=tr('withdrawDisabledWallet'); }
    else if(available<minWithdrawal){ withdrawHint=tr('withdrawDisabledMinimum').replace('{min}', money(minWithdrawal)); }
    else { withdrawDisabled=false; withdrawHint=tr('withdrawMinHint'); }
    if($('withdrawReferral')){
      $('withdrawReferral').disabled=withdrawDisabled;
      $('withdrawReferral').dataset.available=String(available);
      $('withdrawReferral').dataset.minimum=String(minWithdrawal);
    }
    if($('referralWithdrawHint')) $('referralWithdrawHint').textContent=withdrawHint;
    const goal=stats.next_goal||null;
    if($('nextReferralGoal')){
      if(goal){
        $('nextReferralGoal').classList.remove('completed-goal');
        $('nextGoalTitle').textContent=`${tr('level')} ${goal.level}`;
        $('nextGoalRate').textContent=percent(goal.rate_bps);
        const rows=[];
        if(Number(goal.remaining_personal_minor||0)>0) rows.push(`<div><span>• ${money(goal.remaining_personal_minor)} USDT</span><small>${esc(tr('personalDeposit'))}</small></div>`);
        if(Number(goal.remaining_line_minor||0)>0) rows.push(`<div><span>• ${money(goal.remaining_line_minor)} USDT</span><small>${esc(tr('lineTurnoverGoal'))}</small></div>`);
        $('nextGoalRemaining').innerHTML=rows.join('')||`<div><strong>${esc(tr('allLevelsUnlocked'))}</strong></div>`;
      }else{
        $('nextReferralGoal').classList.add('completed-goal');
        $('nextGoalTitle').textContent=tr('allLevelsUnlocked');
        $('nextGoalRate').textContent='✓';
        $('nextGoalRemaining').innerHTML='';
      }
    }
    const members=team.members||[];
    $('teamMembers').innerHTML=members.length?members.map((m)=>`<article class="list-card"><div class="list-card-header"><div><strong>${esc(m.first_name||m.username||m.telegram_id)}</strong><small>${m.username?'@'+esc(m.username)+' · ':''}ID ${esc(m.telegram_id)} · <span class="member-level">${esc(tr('level'))} ${esc(m.level)}</span></small></div><div><strong>${money(m.deposited_minor)} USDT</strong><small>${esc(m.deposit_count||0)} ${esc(tr('deposits').toLowerCase())}</small></div></div></article>`).join(''):`<div class="empty-state">${esc(tr('noMembers'))}</div>`;
  }

  async function withdrawReferral(){
    const stats=(state.team&&state.team.stats)||{};
    const available=Number(stats.available_minor||0), minimum=Number(stats.minimum_withdrawal_minor||1000000);
    if(available<minimum){toast(tr('referralMinimum'),'error');return;}
    if(!stats.payout_address){toast(tr('setPayoutWalletFirst'),'error');switchView('wallet',{push:true});return;}
    const button=$('withdrawReferral');
    button.disabled=true;
    try{
      const key=`refwd-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const result=await api('/api/referrals/withdraw',{method:'POST',headers:{'Idempotency-Key':key}});
      toast(`${tr('withdrawalRequested')}: ${money(result.amount_minor)} USDT`,'success');
      await refreshBootstrap();
      await loadTeam();
    }catch(e){handleApiError(e);await loadTeam();}
    finally{if(button){const s=(state.team&&state.team.stats)||{};button.disabled=Number(s.available_minor||0)<Number(s.minimum_withdrawal_minor||1000000) || !(state.data&&state.data.chain&&state.data.chain.payouts_enabled);}}
  }

  async function copyText(text, successKey){ try{await navigator.clipboard.writeText(String(text));toast(tr(successKey||'copied'),'success');}catch(_){toast(tr('copyFailed'),'error');} }

  async function saveWallet(){
    const address=$('walletInput').value.trim(); if(!/^0x[a-fA-F0-9]{40}$/.test(address)){toast(tr('invalidWallet'),'error');return;}
    const current=((state.data&&state.data.user&&state.data.user.payout_address)||'').trim();
    if(current && current.toLowerCase()!==address.toLowerCase() && !window.confirm(tr('confirmSaveWallet'))) return;
    try{await api('/api/wallet',{method:'POST',body:JSON.stringify({address})});state.walletDirty=false;toast(tr('walletSaved'),'success');await refreshBootstrap();}catch(e){handleApiError(e);}
  }
  function updateDepositForm(data){
    const terms=(data&&data.terms)||(state.data&&state.data.terms)||{};
    const chain=(data&&data.chain)||(state.data&&state.data.chain)||{};
    const user=(data&&data.user)||(state.data&&state.data.user)||{};
    const input=$('depositAmount');
    const min=Number(terms.deposit_min_usdt||1);
    const max=Number(terms.deposit_max_usdt||100000);
    if (input) {
      input.min=String(min);
      if (max) input.max=String(max);
    }
    if ($('depositRangeHint')) {
      $('depositRangeHint').textContent=`${tr('depositRange')}: ${min}–${max} USDT · ${tr('depositOnlyUsdt')}`;
    }
    const hasWallet=Boolean(user.payout_address);
    const depositsOk=Boolean(chain.enabled && chain.deposits_enabled && chain.payouts_enabled && chain.treasury_address);
    if ($('depositWalletGate')) $('depositWalletGate').classList.toggle('hidden', hasWallet);
    if ($('depositChainGate')) {
      $('depositChainGate').classList.toggle('hidden', !hasWallet || depositsOk);
      if (!depositsOk) $('depositChainGate').textContent=tr('depositsDisabledUi');
    }
    const btn=$('createDeposit');
    if (btn) {
      btn.disabled=!hasWallet || !depositsOk;
      if (!depositsOk) btn.title=tr('depositsDisabledUi');
      else if (!hasWallet) btn.title=tr('setPayoutWalletBeforeDeposit');
      else btn.title='';
    }
  }
  async function createDeposit(){
    const amount=Number($('depositAmount').value), terms=(state.data&&state.data.terms)||{}, user=(state.data&&state.data.user)||{}, chain=(state.data&&state.data.chain)||{};
    if (!user.payout_address){toast(tr('setPayoutWalletFirst'),'error');switchView('wallet',{push:true});return;}
    if (!(chain.enabled && chain.deposits_enabled && chain.payouts_enabled && chain.treasury_address)){toast(tr('depositsDisabledUi'),'error');return;}
    if(!Number.isFinite(amount)||amount<Number(terms.deposit_min_usdt||1)||amount>Number(terms.deposit_max_usdt||100000)){toast(`${tr('amount')}: ${terms.deposit_min_usdt||1}–${terms.deposit_max_usdt||100000} USDT`,'error');return;}
    const promoCode=$('depositPromoCode')?$('depositPromoCode').value.trim():'';
    const btn=$('createDeposit'); if(btn){btn.disabled=true;btn.dataset.busy='1';}
    try{
      const key=`invoice-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const body={amount};
      if(promoCode) body.promo_code=promoCode;
      const invoice=await api('/api/deposits/invoice',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify(body)});
      state.activeInvoice=invoice;
      try{sessionStorage.setItem('novera_active_invoice', JSON.stringify(invoice));}catch(_){}
      renderInvoice(invoice);
      if($('depositPromoCode')) $('depositPromoCode').value='';
      const bonusUsdt=Number(invoice.bonus_usdt||0);
      if(promoCode && bonusUsdt>0){
        toast(tr('promoApplied').replace('{bonus}',bonusUsdt.toFixed(2)).replace('{total}',Number(invoice.effective_principal_usdt||amount).toFixed(2)),'success');
      } else {
        toast(tr('invoiceCreated'),'success');
      }
    }catch(e){handleApiError(e);}
    finally{if(btn) btn.dataset.busy='';updateDepositForm(state.data);}
  }
  function stopInvoiceTimer(){
    if(state.invoiceTimer){clearInterval(state.invoiceTimer);state.invoiceTimer=null;}
  }
  function renderInvoice(invoice){
    const box=$('invoiceBox'); if(!box||!invoice)return;
    const address=String(invoice.treasury_address||'');
    const exact=String(invoice.exact_amount||'');
    const amountLabel=`${exact} USDT`;
    const token=String(invoice.token_symbol||'USDT');
    const chainId=invoice.chain_id!=null?String(invoice.chain_id):'—';
    const invoiceId=invoice.id!=null?String(invoice.id):'';
    const expiresAt=Number(invoice.expires_at||0);
    const tick=()=>{
      const now=Math.floor(Date.now()/1000);
      const expired=expiresAt>0 && expiresAt<=now;
      const secondsLeft=expiresAt>0?Math.max(0,expiresAt-now):0;
      const minutesLeft=Math.ceil(secondsLeft/60);
      const countdownLabel=expired
        ? fmtDate(expiresAt)
        : (secondsLeft>=60
            ? `${minutesLeft} ${tr('invoiceMinutes')}`
            : `${secondsLeft} ${tr('invoiceSeconds')}`);
      const statusLabel=expired?tr('invoiceExpired'):tr('invoicePending');
      const statusClass=expired?'failed':'queued';
      const ttlStrong=box.querySelector('[data-invoice-ttl]');
      const statusStrong=box.querySelector('[data-invoice-status]');
      if(ttlStrong) ttlStrong.textContent=countdownLabel;
      if(statusStrong){statusStrong.textContent=statusLabel;statusStrong.className=`tag ${statusClass}`;}
      if(expired) stopInvoiceTimer();
    };
    const reusedNote=invoice.reused?`<div class="invoice-reused">${esc(tr('invoiceReused'))}</div>`:'';
    const bonusUsdt=Number(invoice.bonus_usdt||0);
    const promoLine=bonusUsdt>0?`<div class="invoice-line"><span>${esc(tr('promoBonusLine'))}</span><strong class="amount-positive">+${esc(bonusUsdt.toFixed(2))} USDT</strong></div><div class="invoice-line"><span>${esc(tr('promoEffectivePrincipalLine'))}</span><strong>${esc(Number(invoice.effective_principal_usdt||0).toFixed(2))} USDT</strong></div>`:'';
    const allCopy=`${tr('network')}: BNB Smart Chain (BEP-20)\n${tr('invoiceToken')}: ${token}\n${tr('invoiceChainId')}: ${chainId}\n${tr('invoiceAddressTitle')}: ${address}\n${tr('invoiceExactTitle')}: ${exact}`;
    box.classList.remove('hidden');
    box.innerHTML=`
      <div class="invoice-head">
        <div><p class="overline">${esc(tr('invoiceStatus'))}</p><strong class="tag queued" data-invoice-status>${esc(tr('invoicePending'))}</strong>${invoiceId?`<small class="invoice-id">#${esc(invoiceId)}</small>`:''}</div>
        <div class="invoice-ttl"><span>${esc(tr('invoiceCountdown'))}</span><strong data-invoice-ttl>—</strong></div>
      </div>
      ${reusedNote}
      <div class="invoice-hero-amount">
        <span>${esc(tr('invoiceExactTitle'))}</span>
        <strong class="money">${esc(amountLabel)}</strong>
        <small>${esc(tr('invoiceTailHint'))}</small>
      </div>
      <div class="invoice-line"><span>${esc(tr('network'))}</span><strong>BNB Smart Chain · BEP-20</strong></div>
      <div class="invoice-line"><span>${esc(tr('invoiceToken'))}</span><strong>${esc(token)}</strong></div>
      <div class="invoice-line"><span>${esc(tr('invoiceChainId'))}</span><strong>${esc(chainId)}</strong></div>
      <div class="invoice-line invoice-address-line"><span>${esc(tr('invoiceAddressTitle'))}</span><strong class="invoice-address">${esc(address)}</strong></div>
      <div class="invoice-line"><span>${esc(tr('validUntil'))}</span><strong>${esc(fmtDate(expiresAt))}</strong></div>
      ${promoLine}
      <div class="invoice-actions">
        <button type="button" class="touch-target" data-copy-invoice="amount">${esc(tr('copyAmount'))}</button>
        <button type="button" class="touch-target" data-copy-invoice="address">${esc(tr('copyAddress'))}</button>
        <button type="button" class="touch-target" data-copy-invoice="all">${esc(tr('copyAll'))}</button>
      </div>`;
    box.querySelectorAll('[data-copy-invoice]').forEach((b)=>b.addEventListener('click',()=>{
      const mode=b.dataset.copyInvoice;
      if(mode==='address') copyText(address,'copyAddressDone');
      else if(mode==='amount') copyText(exact,'copyAmountDone');
      else copyText(allCopy,'copyAllDone');
    }));
    stopInvoiceTimer();
    tick();
    state.invoiceTimer=setInterval(tick,1000);
  }

  function showSessionError(){
    $('sessionBanner').classList.remove('hidden');
    const title=$('sessionBanner').querySelector('[data-i18n="sessionTitle"]');
    const text=$('sessionBanner').querySelector('[data-i18n="sessionText"]');
    const hint=$('sessionRecoverHint');
    if (title) title.textContent=tr('sessionTitle');
    if (text) text.textContent=tr('sessionText');
    if (hint) hint.textContent=tr('sessionRecoverHint');
    if($('sessionRecoverCta')) $('sessionRecoverCta').textContent=tr('sessionRecoverCta');
    $('accountState').textContent=tr('error');
  }
  async function handleApiError(e){
    console.debug('NOVERA API error',e&&e.status,e&&e.detail);
    if (e && (e.status===401 || e.status===409)) {
      showSessionError();
      if (e.status===409 || String(e.detail||'').toLowerCase().includes('account context mismatch')) {
        await clearTelegramSession();
      }
    }
    toast(apiErrorText(e&&e.detail,e&&e.status),'error');
  }
  async function refreshBootstrap(){
    if(state.bootstrapInFlight) return state.bootstrapInFlight;
    state.bootstrapInFlight=(async()=>{
      try{
        const data=verifyBootstrapIdentity(await captureAuthSession(await api('/api/bootstrap',{cache:'no-store'})));
        $('sessionBanner').classList.add('hidden');
        render(data,{preserve:true});
        return true;
      }catch(e){
        await handleApiError(e);
        return false;
      }finally{
        state.bootstrapInFlight=null;
      }
    })();
    return state.bootstrapInFlight;
  }
  async function refreshTelegramAccountContext(){
    if (state.accountRefreshBusy) return;
    state.accountRefreshBusy=true;
    try {
      const previousToken=String(state.telegramSessionToken||'');
      const previousUserId=sessionUserId(previousToken) || Number(state.telegramUserId||0);
      const previousLiveId=currentTelegramUserId();
      await loadTelegramSession(true);
      syncTelegramContext();
      const currentToken=String(state.telegramSessionToken||'');
      const currentUserId=sessionUserId(currentToken) || Number(state.telegramUserId||0);
      const currentLiveId=currentTelegramUserId();
      const renderedUserId=Number(state.data&&state.data.auth?state.data.auth.telegram_id:0);

      // Telegram's storage is scoped to the currently logged-in user. A token
      // change is therefore a reliable account-switch signal even when the
      // WebView reused stale initData.
      if (previousToken && currentToken !== previousToken) {
        location.reload();
        return;
      }
      if (previousUserId && currentUserId && previousUserId !== currentUserId) {
        location.reload();
        return;
      }
      if (previousLiveId && currentLiveId && previousLiveId !== currentLiveId) {
        await clearTelegramSession();
        location.reload();
        return;
      }
      if (currentUserId && renderedUserId && currentUserId !== renderedUserId) {
        location.reload();
        return;
      }
      if (currentLiveId && renderedUserId && currentLiveId !== renderedUserId) {
        await clearTelegramSession();
        location.reload();
        return;
      }
      if(document.visibilityState==='visible'&&state.data) await refreshBootstrap();
    } finally { state.accountRefreshBusy=false; }
  }


  function setAdminTab(tab){
    state.adminTab=tab||'overview';
    document.querySelectorAll('.admin-tab').forEach((b)=>b.classList.toggle('active',b.dataset.adminTab===state.adminTab));
    document.querySelectorAll('.admin-section').forEach((s)=>s.classList.toggle('active',s.id===`admin-${state.adminTab}`));
    history.replaceState(null,'',`${location.pathname}?view=admin&tab=${encodeURIComponent(state.adminTab)}`);
    loadAdminTab(state.adminTab);
  }
  async function loadAdmin(tab='overview'){
    if(!state.data||!state.data.auth||!state.data.auth.is_admin)return;
    setAdminTab(tab);
    try{
      const summary=await api('/api/admin/summary');
      state.adminCache.summary=summary;
      state.adminCache.summaryFetchedAt=Math.floor(Date.now()/1000);
      renderAdminSummary(summary);
      if(tab==='overview') await renderAdminOverview(summary);
    }catch(e){handleApiError(e);}
  }
  function renderAdminSummary(s){
    const items=[[tr('users'),s.users,tr('newUsers')+`: +${s.new_users_24h||0}`],[tr('active7d'),s.active_users_7d,tr('investors')+`: ${s.investors||0}`],[tr('activeDeposits'),s.active_deposits,`${money(s.active_principal_minor)} USDT`],[tr('failedPayouts'),s.failed_payouts,`${money(s.queued_minor)} USDT ${tr('waiting').toLowerCase()}`]];
    $('adminSummary').innerHTML=items.map(([k,v,sub])=>`<article class="admin-metric"><span>${esc(k)}</span><strong>${esc(v||0)}</strong><small>${esc(sub)}</small></article>`).join('');
  }
  async function renderAdminOverview(s){
    const net=Number(s.deposited_minor||0)-Number(s.paid_minor||0);
    let safety=null, system=null;
    try{
      [safety, system]=await Promise.all([
        api('/api/admin/safety').catch(()=>null),
        api('/api/admin/system').catch(()=>null)
      ]);
    }catch(_){/* overview still renders money cards */}
    const queue=safety&&safety.queue?safety.queue:{};
    const pendingCount=Number(queue.pending_count||s.failed_payouts||0);
    const pendingMinor=Number(queue.pending_minor||s.queued_minor||0);
    const oldestAge=queue.oldest_age_seconds;
    const circuitOpen=Boolean(safety&&safety.circuit_open);
    const safetyMissing=!safety;
    const safetyStatus=safetyMissing?tr('adminSafetyUnknown'):(safety&&safety.status?String(safety.status):'—');
    const refreshed=state.adminCache.summaryFetchedAt||Math.floor(Date.now()/1000);
    const setup=system&&system.setup?system.setup:(state.data&&state.data.setup)||{};
    const stuckLine=safetyMissing
      ? tr('adminSafetyUnknownHint')
      : (oldestAge==null
        ? tr('adminNoStuck')
        : `${tr('adminStuckQueue')}: ${ageLabel(Math.floor(Date.now()/1000) - Number(oldestAge))}`);
    const circuitClass=safetyMissing?'queued':(circuitOpen?'failed':'confirmed');
    const circuitLabel=safetyMissing?tr('adminSafetyUnknown'):(circuitOpen?tr('adminCircuitOpen'):tr('adminCircuitOk'));
    $('admin-overview').innerHTML=`
      <p class="admin-refresh-meta">${esc(tr('adminLastRefresh'))}: ${esc(fmtDate(refreshed))}</p>
      <div class="overview-grid">
        <article class="panel overview-card"><h3>${esc(tr('deposited'))}</h3><div class="detail-row"><span>${esc(tr('deposited'))}</span><strong>${money(s.deposited_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('today'))}</span><strong>${money(s.deposits_24h_minor)} USDT</strong></div></article>
        <article class="panel overview-card"><h3>${esc(tr('paidOut'))}</h3><div class="detail-row"><span>${esc(tr('paidOut'))}</span><strong>${money(s.paid_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('today'))}</span><strong>${money(s.payouts_24h_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('partnerIncome'))}</span><strong>${money(s.referral_paid_minor)} USDT</strong></div></article>
        <article class="panel overview-card"><h3>${esc(tr('netFlow'))}</h3><p>${money(net)} USDT</p></article>
      </div>
      <article class="panel overview-ops-card">
        <div class="section-row"><div><p class="overline">${esc(tr('adminOpsHealth'))}</p><h3>${esc(tr('adminSafetyStatus'))}: ${esc(safetyStatus)}</h3></div><span class="tag ${circuitClass}">${esc(circuitLabel)}</span></div>
        <div class="detail-row"><span>${esc(tr('adminQueuePending'))}</span><strong>${esc(pendingCount)} · ${money(pendingMinor)} USDT</strong></div>
        <div class="detail-row"><span>${esc(tr('failedPayouts'))}</span><strong>${esc(s.failed_payouts||0)}</strong></div>
        <div class="detail-row"><span>${esc(tr('setupState'))}</span><strong>${esc(setupStatusText(setup.status||'bootstrap'))}</strong></div>
        <p class="field-hint">${esc(stuckLine)}</p>
        <p class="field-hint">${esc(tr('adminRetryHint'))}</p>
      </article>`;
  }
  async function loadAdminTab(tab){
    if(!state.data||!state.data.auth||!state.data.auth.is_admin)return;
    try{
      if(tab==='users')await loadAdminUsers($('adminSearch').value.trim());
      else if(tab==='deposits')await loadAdminDeposits();
      else if(tab==='payouts')await loadAdminPayouts();
      else if(tab==='broadcasts')await loadAdminBroadcasts();
      else if(tab==='campaigns')await loadAdminCampaigns();
      else if(tab==='admins')await loadAdminAdmins();
      else if(tab==='terms')await loadAdminTerms();
      else if(tab==='links')await loadAdminLinks();
      else if(tab==='treasury')await loadAdminTreasury();
      else if(tab==='system')await loadAdminSystem();
      else if(tab==='logs')await loadAdminLogs();
      else if(tab==='overview'&&state.adminCache.summary) await renderAdminOverview(state.adminCache.summary);
    }catch(e){handleApiError(e);}
  }
  async function loadAdminUsers(query=''){
    const users=await api(`/api/admin/users?query=${encodeURIComponent(query)}`);
    state.adminCache.users=users;
    renderAdminUsersList();
  }
  function renderAdminUsersList(){
    const users=state.adminCache.users||[];
    const filter=state.adminUserFilter||'all';
    const filtered=users.filter((u)=>{
      if(filter==='investors') return Number(u.deposit_count||0)>0 || Number(u.active_deposit_count||0)>0;
      if(filter==='blocked') return Boolean(Number(u.blocked)||u.is_blocked);
      return true;
    });
    const meta=`<p class="admin-users-meta">${esc(tr('adminUsersShown').replace('{shown}',String(filtered.length)).replace('{total}',String(users.length)))}</p>`;
    $('adminUsersList').innerHTML=meta+(filtered.length?filtered.map((u)=>`<article class="list-card"><button class="admin-user-btn touch-target" type="button" data-user-id="${esc(u.telegram_id)}"><div class="list-card-header"><div><strong>${esc(u.first_name||u.username||u.telegram_id)}</strong><small>${u.username?'@'+esc(u.username)+' · ':''}ID ${esc(u.telegram_id)} · ${esc(fmtDate(u.created_at))}${u.blocked||u.is_blocked?' · '+esc(tr('accountBlocked')):''}</small></div><div><strong>${money(u.manual_balance_minor)} USDT</strong><small>${esc(tr('accountBalance'))} · ${esc(u.deposit_count||0)} ${esc(tr('deposits').toLowerCase())}</small></div></div></button></article>`).join(''):`<div class="empty-state">${esc(tr('adminUsersEmptyFilter'))}</div>`);
    $('adminUsersList').querySelectorAll('[data-user-id]').forEach((b)=>b.addEventListener('click',()=>{state.adminUserTab='overview';openAdminUser(b.dataset.userId);}));
  }
  async function openAdminUser(id){
    try{const d=await api(`/api/admin/users/${encodeURIComponent(id)}`);renderAdminUserModal(d);$('userModal').classList.remove('hidden');}catch(e){handleApiError(e);}
  }
  function renderAdminUserModal(d){
    state.adminUserDetail=d;
    const u=d.user||{}, stats=d.stats||{}, ref=d.referrer, deposits=d.deposits||[], payouts=d.payouts||[], partners=d.partners||[];
    const adjustments=d.balance_adjustments||[], referrerAdjustments=d.referrer_adjustments||[], referralAdjustments=d.referral_balance_adjustments||[], levelAdjustments=d.referral_level_adjustments||[];
    const manualLevel=Number((d.referral_level_override||{}).unlocked_level||0);
    const name=u.first_name||u.username||u.telegram_id;
    const refLabel=(item)=>item?(item.username?`@${item.username} · ID ${item.telegram_id}`:`${item.first_name||'ID'} ${item.first_name?'· ':''}ID ${item.telegram_id}`):tr('none');
    const adjustmentRows=adjustments.length?adjustments.slice(0,12).map((x)=>`<div class="balance-audit-row"><div><strong>${money(x.new_balance_minor)} USDT</strong><small>${esc(fmtDate(x.created_at))} · ${Number(x.delta_minor||0)>=0?'+':''}${money(x.delta_minor)} USDT</small></div><span>${esc(x.reason||'—')}</span></div>`).join(''):`<div class="empty-state compact">${esc(tr('noBalanceHistory'))}</div>`;
    const refHistory=referrerAdjustments.length?referrerAdjustments.slice(0,10).map((x)=>{
      const oldRef=x.old_referrer_id?{telegram_id:x.old_referrer_id,username:x.old_referrer_username,first_name:x.old_referrer_first_name}:null;
      const newRef=x.new_referrer_id?{telegram_id:x.new_referrer_id,username:x.new_referrer_username,first_name:x.new_referrer_first_name}:null;
      return `<div class="balance-audit-row"><div><strong>${esc(refLabel(newRef))}</strong><small>${esc(fmtDate(x.created_at))}</small></div><span>${esc(tr('from'))}: ${esc(refLabel(oldRef))}</span></div>`;
    }).join(''):`<div class="empty-state compact">${esc(tr('noInviterHistory'))}</div>`;
    const referralBalanceHistory=referralAdjustments.length?referralAdjustments.slice(0,12).map((x)=>`<div class="balance-audit-row"><div><strong>${money(x.new_balance_minor)} USDT</strong><small>${esc(fmtDate(x.created_at))} · ${Number(x.delta_minor||0)>=0?'+':''}${money(x.delta_minor)} USDT</small></div><span>${esc(x.reason||'—')}</span></div>`).join(''):`<div class="empty-state compact">${esc(tr('noReferralBalanceHistory'))}</div>`;
    const levelHistory=levelAdjustments.length?levelAdjustments.slice(0,12).map((x)=>`<div class="balance-audit-row"><div><strong>${esc(x.new_level?`${tr('level')} ${x.new_level}`:tr('automaticQualification'))}</strong><small>${esc(fmtDate(x.created_at))}</small></div><span>${esc(x.reason||'—')}</span></div>`).join(''):`<div class="empty-state compact">${esc(tr('noLevelHistory'))}</div>`;
    const depositRows=deposits.length?deposits.slice(0,40).map((dep)=>`<article class="list-card compact-card"><div class="list-card-header"><div><strong class="money">${money(dep.principal_minor)} USDT</strong><small>#${esc(dep.id)} · ${esc(fmtDate(dep.opened_at))}${dep.source==='admin'?' · '+esc(tr('adminSource')):''}</small></div><span class="tag ${esc(dep.status)}">${esc(statusText(dep.status))}</span></div>${dep.payout_address?`<small class="admin-payout-address">${esc(tr('depositPayoutAddressLabel'))}: ${esc(compactAddress(dep.payout_address))}</small>`:''}${dep.status==='active'?`<div class="admin-actions"><button class="admin-action danger close-admin-investment" type="button" data-deposit-id="${esc(dep.id)}">${esc(tr('closeInvestment'))}</button></div>`:''}</article>`).join(''):`<div class="empty-state compact">${esc(tr('noUserDeposits'))}</div>`;
    const payoutRows=payouts.length?payouts.slice(0,40).map((p)=>`<article class="list-card compact-card"><div class="list-card-header"><div><strong class="money">${money(p.amount_minor)} USDT</strong><small>#${esc(p.id)} · ${esc(p.subtype==='principal'?tr('principalReturn'):(p.kind==='referral'?tr('referral'):tr('daily')))} · ${esc(fmtDate(p.created_at))}</small></div><span class="tag ${esc(p.status)}">${esc(statusText(p.status))}</span></div>${p.address?`<small class="admin-payout-address">${esc(tr('payoutAddressLabel'))}: ${esc(compactAddress(p.address))}</small>`:''}${p.last_error?`<small class="error-line">${esc(p.last_error)}</small>`:''}</article>`).join(''):`<div class="empty-state compact">${esc(tr('noUserPayouts'))}</div>`;
    const openCounts=openPayoutCounts(payouts);
    const walletOpenStrip=`<div class="wallet-open-strip" aria-label="${esc(tr('walletOpenStripTitle'))}"><div><span>${esc(tr('queued'))}</span><strong>${esc(openCounts.queued)}</strong></div><div><span>${esc(tr('signed'))}</span><strong>${esc(openCounts.signed)}</strong></div><div><span>${esc(tr('broadcast'))}</span><strong>${esc(openCounts.broadcast)}</strong></div></div>`;
    const ps=d.partner_stats||{};
    const partnerSummary=`
      <div class="modal-section">
        <h4>${esc(tr('partnerStatsTitle'))}</h4>
        <div class="detail-row"><span>${esc(tr('referralIncome'))}</span><strong class="money">${money(ps.earned_minor)} USDT</strong></div>
        <div class="detail-row"><span>${esc(tr('todayEarned'))}</span><strong class="money">+${money(ps.today_minor)} USDT</strong></div>
        <div class="detail-row"><span>${esc(tr('availableToWithdraw'))}</span><strong class="money">${money(ps.available_minor)} USDT</strong></div>
        <div class="detail-row"><span>${esc(tr('yourInvestments'))}</span><strong class="money">${money(ps.personal_minor)} USDT</strong></div>
        <div class="detail-row"><span>${esc(tr('lineTurnover'))}</span><strong class="money">${money(ps.line_minor)} USDT</strong></div>
        <div class="detail-row"><span>${esc(tr('inTeam'))}</span><strong>${esc(ps.team_count||0)}</strong></div>
        <div class="detail-row"><span>${esc(tr('levelsUnlocked'))}</span><strong>${esc(ps.current_level||0)}/${esc(ps.levels_total||5)}</strong></div>
      </div>`;
    const partnerRows=partners.length?partners.slice(0,100).map((p)=>`
      <article class="list-card compact-card">
        <button class="admin-user-btn touch-target" type="button" data-partner-id="${esc(p.telegram_id)}">
          <div class="list-card-header">
            <div>
              <strong>${esc(p.first_name||p.username||p.telegram_id)}</strong>
              <small>${p.username?'@'+esc(p.username)+' · ':''}ID ${esc(p.telegram_id)} · ${esc(fmtDate(p.created_at))}</small>
            </div>
          </div>
          <div class="detail-row"><span>${esc(tr('personalTurnover'))}</span><strong class="money">${money(p.personal_turnover_minor)} USDT</strong></div>
          <div class="detail-row"><span>${esc(tr('structureTurnover'))}</span><strong class="money">${money(p.structure_turnover_minor)} USDT</strong></div>
          <div class="detail-row"><span>${esc(tr('structureMembers'))}</span><strong>${esc(p.structure_member_count||0)}</strong></div>
        </button>
      </article>`).join(''):`<div class="empty-state compact">${esc(tr('noUserPartners'))}</div>`;
    const tabs=[
      ['overview',tr('userTabOverview')],
      ['investments',tr('userTabInvestments')],
      ['payouts',tr('userTabPayouts')],
      ['referral',tr('userTabReferral')],
      ['access',tr('userTabAccess')],
      ['audit',tr('userTabAudit')]
    ];
    const activeTab=tabs.some((t)=>t[0]===state.adminUserTab)?state.adminUserTab:'overview';
    state.adminUserTab=activeTab;
    const tabButtons=tabs.map(([id,label])=>`<button class="user-modal-tab ${id===activeTab?'active':''}" type="button" data-user-tab="${id}">${esc(label)}</button>`).join('');
    const panel=(id,hint,body)=>`<section class="user-modal-panel ${id===activeTab?'active':''}" data-user-panel="${id}"><p class="field-hint user-tab-hint">${esc(hint)}</p>${body}</section>`;

    const overviewBody=`
      <div class="modal-section"><div class="detail-row"><span>${esc(tr('registered'))}</span><strong>${esc(fmtDate(u.created_at))}</strong></div><div class="detail-row"><span>${esc(tr('status'))}</span><strong>${u.blocked?esc(tr('blocked')):esc(tr('online'))}</strong></div><div class="detail-row"><span>${esc(tr('referrer'))}</span><strong>${esc(refLabel(ref))}</strong></div><div class="detail-row"><span>${esc(tr('payoutAddress'))}</span><strong>${esc(u.payout_address||tr('none'))}</strong></div></div>
      <div class="modal-section"><div class="detail-row"><span>${esc(tr('internalBalance'))}</span><strong class="money">${money(u.manual_balance_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('referralBalanceControl'))}</span><strong class="money">${money(d.referral_balance_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('deposited'))}</span><strong class="money">${money(stats.deposited_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('activeAssets'))}</span><strong class="money">${money(stats.active_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('paidOut'))}</span><strong class="money">${money(stats.paid_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('partnerIncome'))}</span><strong class="money">${money(stats.referral_paid_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('team'))}</span><strong>${esc(partners.length)}</strong></div></div>
      <div class="admin-actions"><button id="toggleUserBlock" class="admin-action ${u.blocked?'success':'danger'}" type="button">${esc(u.blocked?tr('unblock'):tr('block'))}</button></div>`;

    const investmentsBody=`
      <div class="modal-section user-control-section"><h4>${esc(tr('manualInvestment'))}</h4><p class="field-hint">${esc(tr('manualInvestmentNote'))}</p><label class="input-label" for="adminInvestmentAmount">${esc(tr('amount'))}, USDT</label><input id="adminInvestmentAmount" class="text-input" type="number" min="0.000001" step="0.000001" inputmode="decimal" placeholder="USDT"><label class="input-label" for="adminInvestmentReason">${esc(tr('adminReason'))}</label><textarea id="adminInvestmentReason" class="textarea-input compact-textarea" maxlength="500" rows="2" placeholder="${esc(tr('adminReasonHint'))}"></textarea><button id="openAdminInvestment" class="primary-btn compact-primary" type="button">${esc(tr('openInvestment'))}</button></div>
      <div class="modal-section user-control-section"><h4>${esc(tr('closeInvestmentSection'))}</h4><p class="field-hint">${esc(tr('closeInvestmentNote'))}</p><label class="input-label" for="adminCloseInvestmentReason">${esc(tr('adminReason'))}</label><textarea id="adminCloseInvestmentReason" class="textarea-input compact-textarea" maxlength="500" rows="2" placeholder="${esc(tr('adminReasonHint'))}"></textarea></div>
      <div class="modal-section"><h4>${esc(tr('deposits'))}</h4><div class="stack-list compact-list">${depositRows}</div></div>`;

    const payoutsBody=`<div class="modal-section"><div class="stack-list compact-list">${payoutRows}</div></div>`;

    const referralBody=`
      ${partnerSummary}
      <div class="modal-section user-control-section"><h4>${esc(tr('referralBalanceControl'))}</h4><div class="big-balance">${money(d.referral_balance_minor)} <small>USDT</small></div><p class="field-hint">${esc(tr('referralBalanceNote'))}</p><label class="input-label" for="adminReferralBalanceInput">${esc(tr('referralBalanceControl'))}, USDT</label><input id="adminReferralBalanceInput" class="text-input" type="number" min="0" step="0.000001" inputmode="decimal" value="${esc((Number(d.referral_balance_minor||0)/1000000).toFixed(6))}"><label class="input-label" for="adminReferralBalanceReason">${esc(tr('adminReason'))}</label><textarea id="adminReferralBalanceReason" class="textarea-input compact-textarea" maxlength="500" rows="2" placeholder="${esc(tr('adminReasonHint'))}"></textarea><button id="saveAdminReferralBalance" class="primary-btn compact-primary" type="button">${esc(tr('setBalance'))}</button></div>
      <div class="modal-section user-control-section"><h4>${esc(tr('partnerLevelAccess'))}</h4><p class="field-hint">${esc(tr('partnerLevelNote'))}</p><select id="adminReferralLevel" class="text-input"><option value="0" ${manualLevel===0?'selected':''}>${esc(tr('automaticQualification'))}</option>${[1,2,3,4,5].map((level)=>`<option value="${level}" ${manualLevel===level?'selected':''}>${esc(tr('level'))} ${level}</option>`).join('')}</select><label class="input-label" for="adminReferralLevelReason">${esc(tr('adminReason'))}</label><textarea id="adminReferralLevelReason" class="textarea-input compact-textarea" maxlength="500" rows="2" placeholder="${esc(tr('adminReasonHint'))}"></textarea><button id="saveAdminReferralLevel" class="primary-btn compact-primary" type="button">${esc(tr('save'))}</button></div>
      <div class="modal-section"><h4>${esc(tr('members'))}</h4><div class="stack-list compact-list">${partnerRows}</div></div>`;

    const accessBody=`
      <div class="modal-section user-control-section"><h4>${esc(tr('inviterManagement'))}</h4><div class="detail-row"><span>${esc(tr('currentInviter'))}</span><strong>${esc(refLabel(ref))}</strong></div><p class="field-hint">${esc(tr('inviterChangeHint'))}</p><label class="input-label" for="adminReferrerInput">${esc(tr('newInviter'))}</label><input id="adminReferrerInput" class="text-input" maxlength="64" autocomplete="off" value="${esc(ref?(ref.username?'@'+ref.username:String(ref.telegram_id)):'')}" placeholder="${esc(tr('inviterIdentifier'))}"><div class="admin-actions"><button id="saveAdminReferrer" class="admin-action" type="button">${esc(tr('setInviter'))}</button><button id="clearAdminReferrer" class="admin-action danger" type="button">${esc(tr('clearInviter'))}</button></div></div>
      <div class="modal-section user-control-section"><h4>${esc(tr('internalBalance'))}</h4><div class="big-balance">${money(u.manual_balance_minor)} <small>USDT</small></div><p class="field-hint">${esc(tr('manualBalanceNote'))}</p><label class="input-label" for="adminBalanceInput">${esc(tr('internalBalance'))}, USDT</label><input id="adminBalanceInput" class="text-input" type="number" min="0" step="0.000001" inputmode="decimal" value="${esc((Number(u.manual_balance_minor||0)/1000000).toFixed(6))}"><label class="input-label" for="adminBalanceReason">${esc(tr('balanceReason'))}</label><textarea id="adminBalanceReason" class="textarea-input compact-textarea" maxlength="500" rows="2" placeholder="${esc(tr('balanceReasonHint'))}"></textarea><button id="saveAdminBalance" class="primary-btn compact-primary" type="button">${esc(tr('setBalance'))}</button></div>
      <div class="modal-section user-control-section"><h4>${esc(tr('walletManagement'))}</h4><p class="field-hint">${esc(tr('walletManagementHint'))}</p>${walletOpenStrip}<p class="field-hint">${esc(formatPipelineSummary(openCounts))}</p><input id="adminWalletInput" class="text-input" maxlength="42" value="${esc(u.payout_address||'')}" placeholder="0x…"><div class="admin-actions"><button id="saveAdminWallet" class="admin-action" type="button">${esc(tr('save'))}</button><button id="clearAdminWallet" class="admin-action danger" type="button">${esc(tr('clearWallet'))}</button></div></div>
      <div class="admin-actions"><button id="toggleUserBlockAccess" class="admin-action ${u.blocked?'success':'danger'}" type="button">${esc(u.blocked?tr('unblock'):tr('block'))}</button></div>`;

    const auditBody=`
      <div class="modal-section"><h4>${esc(tr('balanceHistory'))}</h4><div class="balance-audit-list">${adjustmentRows}</div></div>
      <div class="modal-section"><h4>${esc(tr('referralBalanceHistory'))}</h4><div class="balance-audit-list">${referralBalanceHistory}</div></div>
      <div class="modal-section"><h4>${esc(tr('levelHistory'))}</h4><div class="balance-audit-list">${levelHistory}</div></div>
      <div class="modal-section"><h4>${esc(tr('inviterHistory'))}</h4><div class="balance-audit-list">${refHistory}</div></div>`;

    $('adminUserDetail').innerHTML=`
      <div class="user-detail-head"><div class="profile-avatar">${esc(String(name)[0]||'U')}</div><div><strong>${esc(name)}</strong><span>${u.username?'@'+esc(u.username)+' · ':''}ID ${esc(u.telegram_id)}</span></div></div>
      <div class="user-modal-tabs" role="tablist">${tabButtons}</div>
      ${panel('overview',tr('userOverviewHint'),overviewBody)}
      ${panel('investments',tr('userInvestmentsHint'),investmentsBody)}
      ${panel('payouts',tr('userPayoutsHint'),payoutsBody)}
      ${panel('referral',tr('userReferralHint'),referralBody)}
      ${panel('access',tr('userAccessHint'),accessBody)}
      ${panel('audit',tr('userAuditHint'),auditBody)}`;

    $('adminUserDetail').querySelectorAll('[data-user-tab]').forEach((btn)=>btn.addEventListener('click',()=>{
      state.adminUserTab=btn.dataset.userTab;
      $('adminUserDetail').querySelectorAll('.user-modal-tab').forEach((el)=>el.classList.toggle('active',el.dataset.userTab===state.adminUserTab));
      $('adminUserDetail').querySelectorAll('.user-modal-panel').forEach((el)=>el.classList.toggle('active',el.dataset.userPanel===state.adminUserTab));
    }));
    $('adminUserDetail').querySelectorAll('[data-partner-id]').forEach((btn)=>{
      btn.addEventListener('click',()=>{
        state.adminUserTab='referral';
        openAdminUser(btn.dataset.partnerId);
      });
    });

    const bindBlock=(el)=>{ if(el) el.addEventListener('click',()=>toggleAdminUserBlock(u.telegram_id,!Boolean(u.blocked))); };
    bindBlock($('toggleUserBlock'));
    bindBlock($('toggleUserBlockAccess'));
    if($('saveAdminBalance')) $('saveAdminBalance').addEventListener('click',()=>setAdminUserBalance(u.telegram_id));
    if($('saveAdminReferralBalance')) $('saveAdminReferralBalance').addEventListener('click',()=>setAdminReferralBalance(u.telegram_id));
    if($('openAdminInvestment')) $('openAdminInvestment').addEventListener('click',()=>openAdminInvestment(u.telegram_id));
    $('adminUserDetail').querySelectorAll('.close-admin-investment').forEach((btn)=>btn.addEventListener('click',()=>closeAdminInvestment(u.telegram_id, Number(btn.dataset.depositId))));
    if($('saveAdminReferralLevel')) $('saveAdminReferralLevel').addEventListener('click',()=>setAdminReferralLevel(u.telegram_id));
    if($('saveAdminWallet')) $('saveAdminWallet').addEventListener('click',()=>setAdminUserWallet(u.telegram_id,$('adminWalletInput').value.trim()));
    if($('clearAdminWallet')) $('clearAdminWallet').addEventListener('click',()=>setAdminUserWallet(u.telegram_id,''));
    if($('saveAdminReferrer')) $('saveAdminReferrer').addEventListener('click',()=>setAdminUserReferrer(u.telegram_id,$('adminReferrerInput').value.trim()));
    if($('clearAdminReferrer')) $('clearAdminReferrer').addEventListener('click',()=>setAdminUserReferrer(u.telegram_id,''));
  }
  async function setAdminUserReferrer(id,identifier){
    const clean=String(identifier||'').trim();
    if(clean && !window.confirm(tr('confirmInviterChange'))) return;
    try{
      await api(`/api/admin/users/${encodeURIComponent(id)}/referrer`,{method:'POST',body:JSON.stringify({identifier:clean||null})});
      toast(clean?tr('inviterChanged'):tr('inviterCleared'),'success');
      await loadAdminUsers($('adminSearch').value.trim());
      await openAdminUser(id);
    }catch(e){handleApiError(e);}
  }
  async function setAdminUserBalance(id){
    const raw=$('adminBalanceInput').value.trim(), reason=$('adminBalanceReason').value.trim();
    const value=Number(raw);
    if(!Number.isFinite(value)||value<0||!reason){toast(tr('invalidData'),'error');return;}
    if(!window.confirm(tr('confirmSetBalance'))) return;
    const key=(crypto.randomUUID?crypto.randomUUID():`bal-${Date.now()}-${Math.random()}`).replace(/-/g,'');
    try{await api(`/api/admin/users/${encodeURIComponent(id)}/balance`,{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({balance_usdt:raw,reason})});toast(tr('balanceSaved'),'success');await loadAdminUsers($('adminSearch').value.trim());await openAdminUser(id);}catch(e){handleApiError(e);}
  }
  async function setAdminReferralBalance(id){
    const raw=$('adminReferralBalanceInput').value.trim(),reason=$('adminReferralBalanceReason').value.trim(),value=Number(raw);
    if(!Number.isFinite(value)||value<0||!reason){toast(tr('invalidData'),'error');return;}
    if(!window.confirm(tr('confirmSetReferralBalance'))) return;
    const key=(crypto.randomUUID?crypto.randomUUID():`refbal-${Date.now()}-${Math.random()}`).replace(/-/g,'');
    try{await api(`/api/admin/users/${encodeURIComponent(id)}/referral-balance`,{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({balance_usdt:raw,reason})});toast(tr('referralBalanceSaved'),'success');await openAdminUser(id);}catch(e){handleApiError(e);}
  }
  async function openAdminInvestment(id){
    const raw=$('adminInvestmentAmount').value.trim(),reason=$('adminInvestmentReason').value.trim(),value=Number(raw);
    if(!Number.isFinite(value)||value<=0||!reason){toast(tr('invalidData'),'error');return;}
    const message=tr('confirmOpenInvestment').replace('{amount}',value.toFixed(6).replace(/0+$/,'').replace(/\.$/,''));
    if(!window.confirm(message))return;
    const fallbackId=`${Date.now()}_${Math.random().toString(36).slice(2)}_${Math.random().toString(36).slice(2)}`;
    const operationId=state.adminInvestmentOps[id]||(window.crypto&&crypto.randomUUID?crypto.randomUUID().replace(/-/g,'_'):fallbackId);
    state.adminInvestmentOps[id]=operationId;
    const button=$('openAdminInvestment');if(button)button.disabled=true;
    try{
      await api(`/api/admin/users/${encodeURIComponent(id)}/investments`,{method:'POST',body:JSON.stringify({amount_usdt:raw,reason,operation_id:operationId,confirm:'OPEN_INVESTMENT'})});
      delete state.adminInvestmentOps[id];toast(tr('investmentOpened'),'success');await loadAdminUsers($('adminSearch').value.trim());await openAdminUser(id);
    }catch(e){if(button)button.disabled=false;handleApiError(e);}
  }
  async function closeAdminInvestment(userId, depositId){
    const reason=($('adminCloseInvestmentReason')&&$('adminCloseInvestmentReason').value.trim())||'';
    if(!depositId||!reason){toast(tr('invalidData'),'error');return;}
    if(!window.confirm(tr('confirmCloseInvestment').replace('{id}',String(depositId)))) return;
    const fallbackId=`${Date.now()}_${Math.random().toString(36).slice(2)}_${Math.random().toString(36).slice(2)}`;
    const opKey=`${userId}:${depositId}`;
    const operationId=state.adminCloseInvestmentOps[opKey]||(window.crypto&&crypto.randomUUID?crypto.randomUUID().replace(/-/g,'_'):fallbackId);
    state.adminCloseInvestmentOps[opKey]=operationId;
    try{
      await api(`/api/admin/users/${encodeURIComponent(userId)}/investments/${encodeURIComponent(depositId)}/close`,{method:'POST',body:JSON.stringify({reason,operation_id:operationId,confirm:'CLOSE_INVESTMENT'})});
      delete state.adminCloseInvestmentOps[opKey];
      toast(tr('investmentClosed'),'success');
      await loadAdminUsers($('adminSearch').value.trim());
      await openAdminUser(userId);
    }catch(e){handleApiError(e);}
  }
  async function setAdminReferralLevel(id){
    const unlocked_level=Number($('adminReferralLevel').value),reason=$('adminReferralLevelReason').value.trim();
    if(!Number.isInteger(unlocked_level)||unlocked_level<0||unlocked_level>5||!reason){toast(tr('invalidData'),'error');return;}
    if(!window.confirm(tr('confirmSetReferralLevel'))) return;
    const key=(crypto.randomUUID?crypto.randomUUID():`reflvl-${Date.now()}-${Math.random()}`).replace(/-/g,'');
    try{await api(`/api/admin/users/${encodeURIComponent(id)}/referral-level`,{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({unlocked_level,reason})});toast(tr('levelAccessSaved'),'success');await openAdminUser(id);}catch(e){handleApiError(e);}
  }
  async function setAdminUserWallet(id,address){
    if(!address && !window.confirm(tr('confirmClearWallet'))) return;
    if(address){
      if(!/^0x[a-fA-F0-9]{40}$/.test(address)){toast(tr('invalidWallet'),'error');return;}
      if(!window.confirm(tr('confirmSaveAdminWallet'))) return;
    }
    try{await api(`/api/admin/users/${encodeURIComponent(id)}/wallet`,{method:'POST',body:JSON.stringify({address:address||null})});toast(tr('walletUpdated'),'success');await openAdminUser(id);}catch(e){handleApiError(e);}
  }
  async function toggleAdminUserBlock(id,blocked){
    if(!window.confirm(blocked?tr('confirmBlockUser'):tr('confirmUnblockUser'))) return;
    try{await api(`/api/admin/users/${id}/block`,{method:'POST',body:JSON.stringify({blocked})});toast(blocked?tr('blockedNow'):tr('unblockedNow'),'success');await loadAdminUsers($('adminSearch').value.trim());await openAdminUser(id);}catch(e){handleApiError(e);}
  }
  async function loadAdminDeposits(){
    const rows=await api('/api/admin/deposits');
    $('adminDepositsList').innerHTML=rows.length?rows.map((d)=>{
      const age=ageLabel(d.opened_at||d.created_at);
      return `<article class="list-card"><div class="list-card-header"><div><strong>${money(d.principal_minor)} USDT</strong><small>${esc(d.first_name||d.username||d.user_id)} · ID ${esc(d.user_id)} · #${esc(d.id)}</small></div><span class="tag ${esc(d.status)}">${esc(statusText(d.status))}</span></div><small>${esc(fmtDate(d.opened_at))}${age?' · '+esc(tr('adminDepositAge'))+' '+esc(age):''}${d.source==='admin'?' · '+esc(tr('adminSource')):(d.tx_hash?' · '+esc(compactAddress(d.tx_hash)):'')}</small></article>`;
    }).join(''):`<div class="empty-state">${esc(tr('noDeposits'))}</div>`;
  }
  async function loadAdminPayouts(){
    const rows=await api('/api/admin/operations');state.adminCache.payouts=rows;renderAdminPayoutRows();
  }
  function renderAdminPayoutRows(){
    const rows=(state.adminCache.payouts||[]).filter((p)=>state.payoutFilter==='all'||p.status==='failed');
    $('adminPayoutsList').innerHTML=(rows.length?rows.map((p)=>{
      const age=ageLabel(p.status_changed_at||p.updated_at||p.created_at);
      const retrySafe=p.status==='failed';
      return `<article class="list-card"><div class="list-card-header"><div><strong>${money(p.amount_minor)} USDT</strong><small>${esc(p.first_name||p.username||p.user_id)} · ${esc(p.admin_test?tr('testPayout'):(p.subtype==='principal'?tr('principalReturn'):(p.kind==='referral'?tr('referral'):tr('daily'))))} · #${esc(p.id)}</small></div><span class="tag ${esc(p.status)}">${esc(statusText(p.status))}</span></div><small>${esc(fmtDate(p.created_at))}${age?' · '+esc(age):''}${p.last_error?' · '+esc(p.last_error):''}</small>${retrySafe?`<div class="admin-actions"><button class="admin-action touch-target" data-retry-payout="${esc(p.id)}" type="button">${esc(tr('retry'))}</button><p class="field-hint">${esc(tr('adminRetryHint'))}</p></div>`:''}</article>`;
    }).join(''):`<div class="empty-state">${esc(tr('noPayouts'))}</div>`)+`<p class="field-hint payout-retry-legend">${esc(tr('adminRetryHint'))}</p>`;
    $('adminPayoutsList').querySelectorAll('[data-retry-payout]').forEach((b)=>b.addEventListener('click',()=>retryPayout(b.dataset.retryPayout)));
  }
  async function retryPayout(id){try{await api(`/api/admin/payouts/${id}/retry`,{method:'POST'});toast(tr('payoutQueued'),'success');await loadAdminPayouts();}catch(e){handleApiError(e);}}
  async function loadAdminBroadcasts(){
    const rows=await api('/api/admin/broadcasts');
    $('adminBroadcastList').innerHTML=rows.length?rows.map((b)=>{
      let buttons=[];try{buttons=JSON.parse(b.buttons_json||'[]')}catch(_){buttons=[]}
      const extras=[b.media_path?'▣ 1':'',buttons.length?`⌁ ${buttons.length}`:''].filter(Boolean).join(' · ');
      const total=Number(b.total_count||0), delivered=Number(b.delivered_count||0), failed=Number(b.failed_count||0);
      const pending=Number(b.pending_count||Math.max(0,total-delivered-failed));
      const progress=total?Math.round((delivered/total)*100):0;
      const retryButton=failed>0?`<div class="admin-actions"><button class="admin-action" type="button" data-retry-broadcast="${esc(b.id)}" data-failed-count="${esc(failed)}">${esc(tr('broadcastRetry'))}</button></div>`:'';
      return `<article class="list-card"><div class="list-card-header"><div><strong>#${esc(b.id)} · ${esc(broadcastAudienceLabel(b.audience))}</strong><small>${esc(fmtDate(b.created_at))}${extras?' · '+esc(extras):''}</small></div><span class="tag ${esc(b.status)}">${esc(statusText(b.status))}</span></div><small class="broadcast-preview-text">${esc(b.message||'')}</small><progress class="broadcast-progress-bar" max="100" value="${progress}"></progress><div class="broadcast-progress"><span>${esc(tr('broadcastDelivered'))}: ${esc(delivered)}</span><span>${esc(tr('broadcastFailed'))}: ${esc(failed)}</span><span>${esc(tr('broadcastPending'))}: ${esc(pending)}</span><span>${esc(tr('broadcastTotal'))}: ${esc(total)}</span></div>${b.last_error?`<small class="error-line">${esc(b.last_error)}</small>`:''}${retryButton}</article>`;
    }).join(''):`<div class="empty-state">${esc(tr('broadcastNone'))}</div>`;
    $('adminBroadcastList').querySelectorAll('[data-retry-broadcast]').forEach((btn)=>btn.addEventListener('click',()=>retryBroadcast(btn.dataset.retryBroadcast,Number(btn.dataset.failedCount||0))));
    await loadBroadcastAudience();
  }
  async function loadAdminCampaigns(){
    const [promos,campaigns]=await Promise.all([api('/api/admin/promo-codes'),api('/api/admin/campaigns')]);
    state.adminCache.promos=promos;
    state.adminCache.campaigns=campaigns;
    renderCampaignPromoOptions();
    renderAdminPromoList();
    renderAdminCampaignList();
  }
  function promoBonusLabel(p){
    return p.bonus_type==='percent'?`${p.bonus_percent||0}%`:`${p.bonus_usdt||0} USDT`;
  }
  function renderCampaignPromoOptions(){
    const select=$('campaignPromo'); if(!select) return;
    const promos=state.adminCache.promos||[];
    const current=select.value;
    select.innerHTML=`<option value="">${esc(tr('campaignPromoNone'))}</option>`+promos.map((p)=>`<option value="${esc(p.id)}">${esc(p.code)} · ${esc(promoBonusLabel(p))}</option>`).join('');
    if(promos.some((p)=>String(p.id)===current)) select.value=current;
  }
  function renderAdminPromoList(){
    const promos=state.adminCache.promos||[];
    $('adminPromoList').innerHTML=promos.length?promos.map((p)=>{
      const minDeposit=Number(p.min_deposit_usdt||0);
      const usedLine=`${esc(tr('promoUsed'))}: ${esc(p.redemption_count||0)}/${esc(p.max_redemptions||0)}`;
      const minLine=minDeposit>0?` · ${esc(tr('promoMinDeposit'))}: ${esc(p.min_deposit_usdt)} USDT`:'';
      return `<article class="list-card"><div class="list-card-header"><div><strong>${esc(p.code)}</strong><small>${esc(promoBonusLabel(p))} · ${usedLine}${minLine}</small></div><span class="tag ${p.enabled?'active':'failed'}">${esc(p.enabled?tr('statusEnabled'):tr('statusDisabled'))}</span></div><div class="admin-actions"><button class="admin-action touch-target" type="button" data-toggle-promo="${esc(p.id)}" data-enabled="${p.enabled?'1':'0'}">${esc(p.enabled?tr('disableAction'):tr('enableAction'))}</button></div></article>`;
    }).join(''):`<div class="empty-state">${esc(tr('promoNone'))}</div>`;
    $('adminPromoList').querySelectorAll('[data-toggle-promo]').forEach((b)=>b.addEventListener('click',()=>togglePromo(b.dataset.togglePromo,b.dataset.enabled==='1')));
  }
  async function togglePromo(id,currentlyEnabled){
    try{
      await api(`/api/admin/promo-codes/${id}`,{method:'PATCH',body:JSON.stringify({enabled:!currentlyEnabled})});
      toast(tr(currentlyEnabled?'promoDisabled':'promoEnabled'),'success');
      await loadAdminCampaigns();
    }catch(e){handleApiError(e);}
  }
  async function createPromo(){
    const code=$('promoCodeInput').value.trim();
    const bonusType=$('promoBonusType').value;
    const bonusValue=Number($('promoBonusValue').value);
    const maxRedemptions=Number($('promoMaxRedemptions').value);
    const minDeposit=Number($('promoMinDeposit').value||0);
    if(!code){toast(tr('promoCodeRequired'),'error');return;}
    if(!Number.isFinite(bonusValue)||bonusValue<=0){toast(tr('promoBonusInvalid'),'error');return;}
    if(!Number.isFinite(maxRedemptions)||maxRedemptions<1){toast(tr('promoMaxInvalid'),'error');return;}
    const payload={code,bonus_type:bonusType,max_redemptions:Math.round(maxRedemptions),min_deposit_usdt:Number.isFinite(minDeposit)?minDeposit:0,enabled:true};
    if(bonusType==='percent') payload.bonus_percent=bonusValue; else payload.bonus_usdt=bonusValue;
    const btn=$('createPromoBtn'); btn.disabled=true;
    try{
      await api('/api/admin/promo-codes',{method:'POST',body:JSON.stringify(payload)});
      toast(tr('promoCreated'),'success');
      $('promoCodeInput').value='';$('promoBonusValue').value='';$('promoMaxRedemptions').value='';$('promoMinDeposit').value='';
      await loadAdminCampaigns();
    }catch(e){handleApiError(e);}finally{btn.disabled=false;}
  }
  function campaignKindLabel(kind){
    if(kind==='promo') return tr('campaignKindPromo');
    if(kind==='partner') return tr('campaignKindPartner');
    return tr('campaignKindCustom');
  }
  function campaignScheduleLabel(c){
    if(c.schedule_mode==='weekly'){
      const keys=['weekdayMon','weekdayTue','weekdayWed','weekdayThu','weekdayFri','weekdaySat','weekdaySun'];
      const days=(c.weekdays||[]).slice().sort((a,b)=>a-b).map((d)=>tr(keys[d]||'')).join(', ');
      return `${tr('campaignScheduleWeekly')} · ${days||'—'} · ${esc(c.time_utc||'')} UTC`;
    }
    return `${tr('campaignScheduleInterval')} · ${esc(c.interval_hours||0)}h`;
  }
  function renderAdminCampaignList(){
    const campaigns=state.adminCache.campaigns||[];
    const promos=state.adminCache.promos||[];
    $('adminCampaignList').innerHTML=campaigns.length?campaigns.map((c)=>{
      const promo=c.promo_code_id?promos.find((p)=>Number(p.id)===Number(c.promo_code_id)):null;
      const promoLine=promo?`<small>${esc(tr('campaignPromoSelect'))}: ${esc(promo.code)}</small>`:'';
      const runLine=`${esc(tr('campaignNextRun'))}: ${esc(fmtDate(c.next_run_at))}${c.last_sent_at?' · '+esc(tr('campaignLastRun'))+': '+esc(fmtDate(c.last_sent_at)):''}`;
      return `<article class="list-card"><div class="list-card-header"><div><strong>${esc(campaignKindLabel(c.kind))} · ${esc(broadcastAudienceLabel(c.audience))}</strong><small>${esc(campaignScheduleLabel(c))}</small></div><span class="tag ${c.enabled?'active':'failed'}">${esc(c.enabled?tr('statusEnabled'):tr('statusDisabled'))}</span></div>${promoLine}<small class="broadcast-preview-text">${esc(c.message_html||'')}</small><small>${runLine}</small><div class="admin-actions"><button class="admin-action touch-target" type="button" data-toggle-campaign="${esc(c.id)}" data-enabled="${c.enabled?'1':'0'}">${esc(c.enabled?tr('disableAction'):tr('enableAction'))}</button><button class="admin-action touch-target" type="button" data-run-campaign="${esc(c.id)}">${esc(tr('runCampaignNow'))}</button></div></article>`;
    }).join(''):`<div class="empty-state">${esc(tr('campaignNone'))}</div>`;
    $('adminCampaignList').querySelectorAll('[data-toggle-campaign]').forEach((b)=>b.addEventListener('click',()=>toggleCampaign(b.dataset.toggleCampaign,b.dataset.enabled==='1')));
    $('adminCampaignList').querySelectorAll('[data-run-campaign]').forEach((b)=>b.addEventListener('click',()=>runCampaignNow(b.dataset.runCampaign)));
  }
  async function toggleCampaign(id,currentlyEnabled){
    try{
      await api(`/api/admin/campaigns/${id}`,{method:'PATCH',body:JSON.stringify({enabled:!currentlyEnabled})});
      toast(tr(currentlyEnabled?'campaignDisabledNotice':'campaignEnabledNotice'),'success');
      await loadAdminCampaigns();
    }catch(e){handleApiError(e);}
  }
  async function runCampaignNow(id){
    try{
      const res=await api(`/api/admin/campaigns/${id}/run`,{method:'POST'});
      if(res && res.status==='sent') toast(tr('campaignRunSent'),'success');
      else toast(`${tr('campaignRunSkipped')}${res&&res.reason?': '+res.reason:''}`,'error');
      await loadAdminCampaigns();
    }catch(e){handleApiError(e);}
  }
  function updateCampaignScheduleFields(){
    const weekly=$('campaignScheduleMode').value==='weekly';
    $('campaignWeekdaysRow').classList.toggle('hidden',!weekly);
    $('campaignIntervalField').classList.toggle('hidden',weekly);
  }
  async function createCampaign(){
    const kind=$('campaignKind').value;
    const audience=$('campaignAudience').value;
    const scheduleMode=$('campaignScheduleMode').value;
    const intervalHours=Number($('campaignIntervalHours').value||24);
    const timeUtc=$('campaignTimeUtc').value.trim()||'12:00';
    const message=$('campaignMessage').value.trim();
    const promoSelect=$('campaignPromo').value;
    const enabled=$('campaignEnabledInput').checked;
    const weekdays=Array.from($('campaignWeekdaysRow').querySelectorAll('.segment.active')).map((b)=>Number(b.dataset.weekday));
    if(!message){toast(tr('campaignMessageRequired'),'error');return;}
    if(kind==='promo' && !promoSelect){toast(tr('campaignPromoRequired'),'error');return;}
    if(scheduleMode==='weekly' && !weekdays.length){toast(tr('campaignWeekdaysRequired'),'error');return;}
    if(!/^\d{1,2}:\d{2}$/.test(timeUtc)){toast(tr('campaignTimeInvalid'),'error');return;}
    const payload={kind,audience,schedule_mode:scheduleMode,interval_hours:Math.max(1,Math.round(intervalHours)||24),weekdays,time_utc:timeUtc,message_html:message,enabled};
    if(promoSelect) payload.promo_code_id=Number(promoSelect);
    const btn=$('createCampaignBtn'); btn.disabled=true;
    try{
      await api('/api/admin/campaigns',{method:'POST',body:JSON.stringify(payload)});
      toast(tr('campaignCreated'),'success');
      $('campaignMessage').value='';
      await loadAdminCampaigns();
    }catch(e){handleApiError(e);}finally{btn.disabled=false;}
  }
  // Mirrors _TelegramHTMLSanitizer in delta_backend/api.py: unknown tags are
  // dropped while their text survives, and only safe-scheme <a href> is kept.
  const TELEGRAM_HTML_TAGS=['b','strong','i','em','u','ins','s','strike','del','code','pre','a'];
  const TELEGRAM_LINK_SCHEMES=/^(https?:\/\/|tg:\/\/)/i;
  // The backend escapes text with quote=False, so quotes must stay literal for
  // the preview length to match the payload Telegram receives.
  const escTelegramText=(v)=>String(v??'').replace(/[&<>]/g,(c)=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  function sanitizeTelegramHtml(raw){
    const source=String(raw||'');
    if(!source.trim()) return '';
    const root=new DOMParser().parseFromString(source,'text/html').body;
    if(!root) return '';
    const parts=[];
    const walk=(node)=>{
      Array.prototype.forEach.call(node.childNodes,(child)=>{
        if(child.nodeType===Node.TEXT_NODE){parts.push(escTelegramText(child.nodeValue||''));return;}
        if(child.nodeType!==Node.ELEMENT_NODE) return;
        const tag=String(child.tagName||'').toLowerCase();
        if(!TELEGRAM_HTML_TAGS.includes(tag)){walk(child);return;}
        if(tag==='a'){
          const href=String(child.getAttribute('href')||'').trim();
          if(!TELEGRAM_LINK_SCHEMES.test(href)){walk(child);return;}
          parts.push(`<a href="${esc(href)}">`);walk(child);parts.push('</a>');
          return;
        }
        parts.push(`<${tag}>`);walk(child);parts.push(`</${tag}>`);
      });
    };
    walk(root);
    return parts.join('').trim();
  }
  function broadcastPreviewButtons(){
    return state.broadcastButtons
      .map((item)=>({text:String(item.text||'').trim(),url:String(item.url||'').trim()}))
      .filter((item)=>item.text&&item.url);
  }
  function renderBroadcastPreview(){
    const textNode=$('broadcastPreviewText'), input=$('broadcastText');
    if(!textNode||!input) return;
    const safe=sanitizeTelegramHtml(input.value);
    const buttons=broadcastPreviewButtons();
    const hasImage=Boolean(state.broadcastImageUrl);
    textNode.innerHTML=safe||`<span class="telegram-preview-empty">${esc(tr('broadcastPreviewEmpty'))}</span>`;
    const image=$('broadcastPreviewImage');
    if(image){
      if(hasImage){image.src=state.broadcastImageUrl;image.classList.remove('hidden');}
      else{image.removeAttribute('src');image.classList.add('hidden');}
    }
    const buttonsNode=$('broadcastPreviewButtons');
    if(buttonsNode){
      buttonsNode.innerHTML=buttons.map((item)=>`<span class="telegram-preview-button">${esc(item.text)}</span>`).join('');
    }
    if($('broadcastLengthHint')) $('broadcastLengthHint').textContent=tr('broadcastLength').replace('{length}',String(safe.length));
    const notice=$('broadcastPreviewNotice');
    if(notice){
      const splits=hasImage&&safe.length>1024;
      notice.textContent=splits?tr('broadcastCaptionSplit'):'';
      notice.classList.toggle('hidden',!splits);
    }
  }
  function broadcastAudienceLabel(audience){
    const map={all:'audienceAll',investors:'audienceInvestors',partners:'audiencePartners'};
    return map[audience]?tr(map[audience]):String(audience||'');
  }
  function renderBroadcastAudienceCount(){
    const node=$('broadcastAudienceCount'), select=$('broadcastAudience');
    if(!node||!select) return;
    const counts=state.broadcastAudience;
    const audience=select.value;
    if(!counts||typeof counts[audience]!=='number'){node.textContent=tr('broadcastAudienceUnknown');return;}
    node.textContent=tr('broadcastAudienceCount').replace('{count}',String(counts[audience]));
  }
  async function loadBroadcastAudience(){
    try{state.broadcastAudience=await api('/api/admin/broadcasts/audience');}catch(_){state.broadcastAudience=null;}
    renderBroadcastAudienceCount();
  }
  function wrapBroadcastSelection(tag){
    const el=$('broadcastText'), start=el.selectionStart||0, end=el.selectionEnd||0, value=el.value;
    if(start===end){toast(tr('formatHint'),'info');el.focus();return;}
    const open=`<${tag}>`,close=`</${tag}>`;
    el.value=value.slice(0,start)+open+value.slice(start,end)+close+value.slice(end);
    el.focus();el.setSelectionRange(start+open.length,end+open.length);
  }
  function formatBroadcastLink(){
    const el=$('broadcastText'), start=el.selectionStart||0, end=el.selectionEnd||0;
    if(start===end){toast(tr('formatHint'),'info');el.focus();return;}
    const url=window.prompt(tr('linkUrl'),'https://');
    if(!url)return;
    if(!/^(https?:\/\/|tg:\/\/)/i.test(url.trim())){toast(tr('invalidButton'),'error');return;}
    const value=el.value,open=`<a href="${esc(url.trim())}">`,close='</a>';
    el.value=value.slice(0,start)+open+value.slice(start,end)+close+value.slice(end);
    el.focus();el.setSelectionRange(start+open.length,end+open.length);
  }
  function clearBroadcastImage(){
    if(state.broadcastImageUrl){URL.revokeObjectURL(state.broadcastImageUrl);state.broadcastImageUrl='';}
    state.broadcastImageFile=null;$('broadcastImage').value='';$('broadcastImagePreview').classList.add('hidden');$('broadcastImageThumb').removeAttribute('src');$('broadcastImageName').textContent='';$('broadcastImageSize').textContent='';
    renderBroadcastPreview();
  }
  function selectBroadcastImage(){
    const file=$('broadcastImage').files&&$('broadcastImage').files[0];if(!file){clearBroadcastImage();return;}
    if(!['image/jpeg','image/png'].includes(file.type)){toast(tr('imageType'),'error');clearBroadcastImage();return;}
    if(file.size>5*1024*1024){toast(tr('imageTooLarge'),'error');clearBroadcastImage();return;}
    clearBroadcastImage();state.broadcastImageFile=file;state.broadcastImageUrl=URL.createObjectURL(file);$('broadcastImageThumb').src=state.broadcastImageUrl;$('broadcastImageName').textContent=file.name;$('broadcastImageSize').textContent=`${(file.size/1024/1024).toFixed(2)} MB`;$('broadcastImagePreview').classList.remove('hidden');
    renderBroadcastPreview();
  }
  function renderBroadcastButtons(){
    const root=$('broadcastButtonsBuilder');
    root.innerHTML=state.broadcastButtons.map((item,index)=>`<div class="broadcast-button-row" data-button-index="${index}"><input class="text-input" data-button-text="${index}" maxlength="64" placeholder="${esc(tr('buttonText'))}" value="${esc(item.text||'')}"><input class="text-input" data-button-url="${index}" maxlength="2048" placeholder="${esc(tr('buttonUrl'))}" value="${esc(item.url||'')}"><button class="icon-btn small danger" type="button" data-remove-broadcast-button="${index}" aria-label="${esc(tr('remove'))}">×</button></div>`).join('');
    root.querySelectorAll('[data-button-text]').forEach((el)=>el.addEventListener('input',()=>{state.broadcastButtons[Number(el.dataset.buttonText)].text=el.value;renderBroadcastPreview();}));
    root.querySelectorAll('[data-button-url]').forEach((el)=>el.addEventListener('input',()=>{state.broadcastButtons[Number(el.dataset.buttonUrl)].url=el.value;renderBroadcastPreview();}));
    root.querySelectorAll('[data-remove-broadcast-button]').forEach((el)=>el.addEventListener('click',()=>{state.broadcastButtons.splice(Number(el.dataset.removeBroadcastButton),1);renderBroadcastButtons();}));
    if($('addBroadcastButton'))$('addBroadcastButton').disabled=state.broadcastButtons.length>=8;
    renderBroadcastPreview();
  }
  function addBroadcastButton(){if(state.broadcastButtons.length>=8)return;state.broadcastButtons.push({text:'',url:'https://'});renderBroadcastButtons();}
  function fileToBase64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||'').split(',',2)[1]||'');reader.onerror=()=>reject(reader.error||new Error('read'));reader.readAsDataURL(file);});}
  async function uploadBroadcastImage(){
    if(!state.broadcastImageFile)return null;
    const data=await fileToBase64(state.broadcastImageFile);
    const result=await api('/api/admin/broadcast-media',{method:'POST',body:JSON.stringify({mime_type:state.broadcastImageFile.type,data_base64:data})});
    return result.media_id;
  }
  async function sendBroadcast(){
    const message=$('broadcastText').value.trim(),audience=$('broadcastAudience').value;
    const buttons=state.broadcastButtons.map((x)=>({text:String(x.text||'').trim(),url:String(x.url||'').trim()}));
    if(!message&&!state.broadcastImageFile){toast(tr('broadcastRequiresContent'),'error');return;}
    if(buttons.some((x)=>!x.text||!x.url||!/^(https?:\/\/|tg:\/\/)/i.test(x.url))){toast(tr('invalidButton'),'error');return;}
    const counts=state.broadcastAudience;
    const recipients=counts&&typeof counts[audience]==='number'?counts[audience]:null;
    if(recipients===0){toast(tr('broadcastNoRecipients'),'error');return;}
    const confirmText=tr('broadcastConfirmSend')
      .replace('{audience}',broadcastAudienceLabel(audience))
      .replace('{count}',recipients===null?'?':String(recipients));
    if(!window.confirm(confirmText)) return;
    const btn=$('sendBroadcast');btn.disabled=true;
    try{const media_id=await uploadBroadcastImage();await api('/api/admin/broadcasts',{method:'POST',body:JSON.stringify({message,audience,media_id,buttons})});$('broadcastText').value='';state.broadcastButtons=[];renderBroadcastButtons();clearBroadcastImage();toast(tr('broadcastSent'),'success');await loadAdminBroadcasts();}catch(e){handleApiError(e);}finally{btn.disabled=false;}
  }
  async function sendBroadcastTest(){
    const message=$('broadcastText').value.trim();
    if(!sanitizeTelegramHtml(message)){toast(tr('broadcastTestNeedsText'),'error');return;}
    const btn=$('testBroadcast');if(btn)btn.disabled=true;
    try{
      await api('/api/admin/broadcasts/test',{method:'POST',body:JSON.stringify({message})});
      toast(tr('broadcastTestQueued'),'success');
    }catch(e){handleApiError(e);}
    finally{if(btn)btn.disabled=false;}
  }
  async function retryBroadcast(id,failedCount){
    const confirmText=tr('broadcastRetryConfirm').replace('{count}',String(failedCount||0));
    if(!window.confirm(confirmText)) return;
    try{
      const result=await api(`/api/admin/broadcasts/${encodeURIComponent(id)}/retry`,{method:'POST'});
      const requeued=Number(result&&result.requeued||0);
      toast(requeued?tr('broadcastRetryQueued').replace('{count}',String(requeued)):tr('broadcastRetryNothing'),requeued?'success':'info');
      await loadAdminBroadcasts();
    }catch(e){handleApiError(e);}
  }
  async function loadAdminAdmins(){
    const rows=await api('/api/admin/admins');
    state.adminCache.admins=rows;
    const isOwner=Boolean(state.data&&state.data.auth&&state.data.auth.is_owner);
    const notice=`<article class="panel owner-model-card" role="note"><div class="form-heading"><span class="form-icon">🛡</span><div><strong>${esc(tr('ownerModelTitle'))}</strong><small>${esc(tr('ownerModelHint'))}</small></div></div>${isOwner?'':`<p class="field-hint">${esc(tr('ownerOnlyGrant'))}</p>`}</article>`;
    $('adminAdminsList').innerHTML=notice+(rows.length?rows.map((a)=>{
      const name=a.first_name||a.username||a.telegram_id;
      const source=a.protected?tr('protectedOwnerBadge'):tr('dynamicSource');
      const removeButton=isOwner&&!a.protected && Number(a.telegram_id)!==Number(state.data&&state.data.auth&&state.data.auth.telegram_id)
        ? `<button class="admin-action danger touch-target" type="button" data-remove-admin="${esc(a.telegram_id)}">${esc(tr('removeAdmin'))}</button>`
        : (a.protected?`<p class="field-hint">${esc(tr('cannotRemoveOwner'))}</p>`:'');
      return `<article class="list-card"><div class="list-card-header"><div><strong>${esc(name)}</strong><small>${a.username?'@'+esc(a.username)+' · ':''}ID ${esc(a.telegram_id)}</small></div><span class="admin-source ${a.protected?'protected':'dynamic'}">${esc(source)}</span></div><div class="admin-badge-row"><span class="admin-source dynamic">${esc(tr('fullAdmin'))}</span>${a.granted_at?`<span class="date-text">${esc(fmtDate(a.granted_at))}</span>`:''}</div>${removeButton?`<div class="admin-actions">${removeButton}</div>`:''}</article>`;
    }).join(''):`<div class="empty-state">${esc(tr('noAdmins'))}</div>`);
    if($('adminGrantInput'))$('adminGrantInput').disabled=!isOwner;
    if($('grantAdminBtn'))$('grantAdminBtn').disabled=!isOwner;
    $('adminAdminsList').querySelectorAll('[data-remove-admin]').forEach((b)=>b.addEventListener('click',()=>removeAdminAccess(b.dataset.removeAdmin)));
  }
  async function addAdminAccess(){
    const identifier=$('adminGrantInput').value.trim();
    if(!identifier){toast(tr('invalidAdmin'),'error');return;}
    if(!(state.data&&state.data.auth&&state.data.auth.is_owner)){toast(tr('ownerOnlyGrant'),'error');return;}
    try{
      await api('/api/admin/admins',{method:'POST',body:JSON.stringify({identifier})});
      $('adminGrantInput').value='';
      toast(tr('adminAdded'),'success');
      await loadAdminAdmins();
    }catch(e){handleApiError(e);}
  }
  async function removeAdminAccess(id){
    if(!(state.data&&state.data.auth&&state.data.auth.is_owner)){toast(tr('ownerOnlyGrant'),'error');return;}
    if(!window.confirm(tr('confirmRemoveAdmin').replace('{id}',String(id)))) return;
    try{
      await api(`/api/admin/admins/${encodeURIComponent(id)}`,{method:'DELETE'});
      toast(tr('adminRemoved'),'success');
      await loadAdminAdmins();
    }catch(e){handleApiError(e);}
  }

  const settingInput=(id,label,value,attrs='')=>`<label class="settings-field"><span>${esc(label)}</span><input id="${id}" class="text-input" value="${esc(value)}" ${attrs}></label>`;
  async function loadAdminTerms(){
    const x=await api('/api/admin/settings');state.adminCache.settings=x;
    const levels=Array.from({length:5},(_,i)=>`<div class="settings-level"><strong>${esc(tr('level'))} ${i+1}</strong>${settingInput(`settingLevelRate${i}`,tr('levelRate'),(Number((x.referral_level_bps||[])[i]||0)/100).toFixed(2),'type="number" min="0" max="100" step="0.01" inputmode="decimal"')}${settingInput(`settingPersonal${i}`,tr('personalThreshold'),(x.referral_personal_thresholds_usdt||[])[i]||0,'type="number" min="0" step="1" inputmode="numeric"')}${settingInput(`settingLine${i}`,tr('lineThreshold'),(x.referral_line_thresholds_usdt||[])[i]||0,'type="number" min="0" step="1" inputmode="numeric"')}</div>`).join('');
    $('admin-terms').innerHTML=`<article class="panel settings-card"><div class="form-heading"><span class="form-icon">⚙</span><div><strong>${esc(tr('settingsTitle'))}</strong><small>${esc(tr('settingsHint'))}</small></div></div><section class="settings-section"><h3>${esc(tr('profitSettings'))}</h3><div class="settings-grid">${settingInput('settingDailyRate',tr('dailyRatePercent'),(Number(x.daily_profit_bps||0)/100).toFixed(2),'type="number" min="0.01" max="100" step="0.01" inputmode="decimal"')}${settingInput('settingPayoutDays',tr('payoutDays'),x.payout_days,'type="number" min="1" max="20" step="1" inputmode="numeric"')}${settingInput('settingDepositMin',tr('depositMin'),x.deposit_min_usdt,'type="number" min="1" step="1" inputmode="numeric"')}${settingInput('settingDepositMax',tr('depositMax'),x.deposit_max_usdt,'type="number" min="1" step="1" inputmode="numeric"')}${settingInput('settingInvoiceTtl',tr('invoiceTtl'),x.invoice_ttl_minutes,'type="number" min="1" max="1440" step="1" inputmode="numeric"')}</div></section><section class="settings-section"><h3>${esc(tr('operationsSettings'))}</h3><div class="settings-switches"><label class="switch-row"><span>${esc(tr('acceptDeposits'))}</span><input id="settingDepositsEnabled" type="checkbox" ${x.deposits_enabled?'checked':''}></label><label class="switch-row"><span>${esc(tr('enablePayouts'))}</span><input id="settingPayoutsEnabled" type="checkbox" ${x.payouts_enabled?'checked':''}></label></div><div class="settings-grid">${settingInput('settingConfirmations',tr('confirmationBlocksLabel'),x.confirmation_blocks,'type="number" min="0" max="100" step="1" inputmode="numeric"')}${settingInput('settingScanInterval',tr('scanIntervalSeconds'),x.deposit_scan_interval_seconds,'type="number" min="1" max="3600" step="1" inputmode="numeric"')}${settingInput('settingSupportUrl',tr('supportUrl'),x.support_url||'','type="url"')}${settingInput('settingChatUrl',tr('chatUrl'),x.chat_url||'','type="url"')}</div></section><section class="settings-section"><h3>${esc(tr('referralSettings'))}</h3><div class="settings-levels">${levels}</div></section><button id="saveRuntimeSettings" class="primary-btn" type="button">${esc(tr('saveSettings'))}</button></article>`;
    const switches=$('admin-terms').querySelector('.settings-switches');
    switches.insertAdjacentHTML('beforeend',`<label class="switch-row"><span>${esc(tr('investmentsEnabled'))}</span><input id="settingInvestmentsEnabled" type="checkbox" ${x.investments_enabled?'checked':''}></label><label class="switch-row"><span>${esc(tr('referralsEnabled'))}</span><input id="settingReferralEnabled" type="checkbox" ${x.referral_enabled?'checked':''}></label>`);
    const isOwner=Boolean(state.data&&state.data.auth&&state.data.auth.is_owner);
    if(!isOwner){$('saveRuntimeSettings').disabled=true;$('saveRuntimeSettings').insertAdjacentHTML('afterend',`<p class="field-hint">${esc(tr('ownerRequired'))}</p>`);}
    $('saveRuntimeSettings').addEventListener('click',saveAdminSettings);
  }
  function numberValue(id){const value=Number($(id).value);if(!Number.isFinite(value))throw new Error('invalid');return value;}
  async function saveAdminSettings(){
    let payload;
    try{
      payload={daily_profit_bps:Math.round(numberValue('settingDailyRate')*100),payout_days:Math.round(numberValue('settingPayoutDays')),deposit_min_usdt:Math.round(numberValue('settingDepositMin')),deposit_max_usdt:Math.round(numberValue('settingDepositMax')),invoice_ttl_minutes:Math.round(numberValue('settingInvoiceTtl')),referral_level_bps:Array.from({length:5},(_,i)=>Math.round(numberValue(`settingLevelRate${i}`)*100)),referral_personal_thresholds_usdt:Array.from({length:5},(_,i)=>Math.round(numberValue(`settingPersonal${i}`))),referral_line_thresholds_usdt:Array.from({length:5},(_,i)=>Math.round(numberValue(`settingLine${i}`))),deposits_enabled:$('settingDepositsEnabled').checked,payouts_enabled:$('settingPayoutsEnabled').checked,confirmation_blocks:Math.round(numberValue('settingConfirmations')),deposit_scan_interval_seconds:Math.round(numberValue('settingScanInterval')),support_url:$('settingSupportUrl').value.trim(),chat_url:$('settingChatUrl').value.trim()};
      payload.investments_enabled=$('settingInvestmentsEnabled').checked;
      payload.referral_enabled=$('settingReferralEnabled').checked;
      if(payload.deposit_min_usdt<1||payload.deposit_max_usdt<payload.deposit_min_usdt||payload.payout_days<1||payload.payout_days>20||!payload.support_url||!payload.chat_url){throw new Error('invalid');}
    }catch(_){toast(tr('invalidData'),'error');return;}
    const btn=$('saveRuntimeSettings');btn.disabled=true;
    try{await api('/api/admin/settings',{method:'POST',body:JSON.stringify(payload)});toast(tr('settingsSaved'),'success');await refreshBootstrap();await loadAdminTerms();}catch(e){handleApiError(e);}finally{btn.disabled=false;}
  }
  function isEditableUrl(value){return /^(https?:\/\/|tg:\/\/)/i.test(String(value||'').trim());}
  function runtimeSettingsPayload(current, overrides={}){
    return Object.assign({
      daily_profit_bps:Number(current.daily_profit_bps||0),
      payout_days:Number(current.payout_days||0),
      deposit_min_usdt:Number(current.deposit_min_usdt||0),
      deposit_max_usdt:Number(current.deposit_max_usdt||0),
      invoice_ttl_minutes:Number(current.invoice_ttl_minutes||0),
      referral_level_bps:Array.from(current.referral_level_bps||[]).map(Number),
      referral_personal_thresholds_usdt:Array.from(current.referral_personal_thresholds_usdt||[]).map(Number),
      referral_line_thresholds_usdt:Array.from(current.referral_line_thresholds_usdt||[]).map(Number),
      deposits_enabled:Boolean(current.deposits_enabled),
      investments_enabled:Boolean(current.investments_enabled),
      payouts_enabled:Boolean(current.payouts_enabled),
      referral_enabled:Boolean(current.referral_enabled),
      confirmation_blocks:Number(current.confirmation_blocks||0),
      deposit_scan_interval_seconds:Number(current.deposit_scan_interval_seconds||0),
      support_url:String(current.support_url||''),
      chat_url:String(current.chat_url||'')
    },overrides);
  }
  async function loadAdminLinks(){
    const x=await api('/api/admin/settings');
    state.adminCache.settings=x;
    $('admin-links').innerHTML=`<article class="panel settings-card links-settings-card"><div class="form-heading"><span class="form-icon">↗</span><div><strong>${esc(tr('linksSettings'))}</strong><small>${esc(tr('linksSettingsHint'))}</small></div></div><p class="field-hint">${esc(tr('linksAuditHint'))}</p><div class="links-editor"><label class="settings-field"><span>${esc(tr('supportLink'))}</span><div class="link-edit-row"><input id="adminSupportLink" class="text-input" type="url" inputmode="url" autocomplete="url" value="${esc(x.support_url||'')}" placeholder="https://t.me/..." aria-describedby="linksAuditNote"><button id="previewSupportLink" class="compact-btn touch-target" type="button">${esc(tr('openLink'))}</button></div></label><label class="settings-field"><span>${esc(tr('chatLink'))}</span><div class="link-edit-row"><input id="adminChatLink" class="text-input" type="url" inputmode="url" autocomplete="url" value="${esc(x.chat_url||'')}" placeholder="https://t.me/..."><button id="previewChatLink" class="compact-btn touch-target" type="button">${esc(tr('openLink'))}</button></div></label></div><div class="links-preview" aria-label="${esc(tr('linksPreviewHint'))}"><span>${esc(tr('linksPreviewHint'))}</span><div><button type="button" class="secondary-btn preview-only" tabindex="-1" aria-hidden="true">? ${esc(tr('support'))}</button><button type="button" class="secondary-btn preview-only" tabindex="-1" aria-hidden="true">✦ ${esc(tr('chat'))}</button></div></div><button id="saveProfileLinks" class="primary-btn touch-target" type="button">${esc(tr('saveLinks'))}</button><p id="linksAuditNote" class="field-hint">${esc(tr('linksAuditHint'))}</p></article>`;
    $('previewSupportLink').addEventListener('click',()=>{const url=$('adminSupportLink').value.trim();if(isEditableUrl(url))openExternal(url);else toast(tr('invalidUrl'),'error');});
    $('previewChatLink').addEventListener('click',()=>{const url=$('adminChatLink').value.trim();if(isEditableUrl(url))openExternal(url);else toast(tr('invalidUrl'),'error');});
    $('saveProfileLinks').addEventListener('click',saveAdminLinks);
  }
  async function saveAdminLinks(){
    const support_url=$('adminSupportLink').value.trim(), chat_url=$('adminChatLink').value.trim();
    if(!isEditableUrl(support_url)||!isEditableUrl(chat_url)){toast(tr('invalidUrl'),'error');return;}
    const btn=$('saveProfileLinks');btn.disabled=true;
    try{
      const current=state.adminCache.settings||await api('/api/admin/settings');
      const payload=runtimeSettingsPayload(current,{support_url,chat_url});
      const saved=await api('/api/admin/settings',{method:'POST',body:JSON.stringify(payload)});
      state.adminCache.settings=saved;
      toast(tr('linksSaved'),'success');
      await refreshBootstrap();
      await loadAdminLinks();
    }catch(e){handleApiError(e);}finally{if($('saveProfileLinks'))$('saveProfileLinks').disabled=false;}
  }

  async function loadAdminTreasury(){
    const [x,tests]=await Promise.all([api('/api/admin/treasury'),api('/api/admin/treasury/test-payouts')]);
    const explorer=String(x.explorer_tx_url||'');
    const rows=tests.length?tests.map((p)=>{
      const tx=String(p.tx_hash||'');
      const txBtn=tx&&explorer?`<button type="button" class="compact-btn" data-test-payout-tx="${esc(tx)}">${esc(tr('openExplorer'))}</button>`:'';
      return `<article class="list-card test-payout-row"><div class="list-card-header"><div><strong>${money(p.amount_minor)} USDT</strong><small>${esc(compactAddress(p.address))} · #${esc(p.id)}</small></div><span class="tag ${esc(p.status)}">${esc(statusText(p.status))}</span></div><small>${esc(fmtDate(p.created_at))}${p.last_error?' · '+esc(p.last_error):''}</small>${txBtn}</article>`;
    }).join(''):`<div class="empty-state">${esc(tr('testPayoutNone'))}</div>`;
    const enabled=Boolean(x.enabled&&x.payouts_enabled&&!x.simulate_payouts);
    $('admin-treasury').innerHTML=`<article class="panel detail-list"><div class="detail-row"><span>${esc(tr('treasury'))}</span><strong>${esc(x.address||tr('none'))}</strong></div><div class="detail-row"><span>USDT</span><strong>${esc(x.token_balance||'—')} ${esc(x.token_symbol||'USDT')}</strong></div><div class="detail-row"><span>BNB</span><strong>${esc(x.native_balance||'—')} BNB</strong></div><div class="detail-row"><span>Chain ID</span><strong>${esc(x.chain_id||'—')}</strong></div></article>
      <article class="panel settings-card test-payout-card"><div class="form-heading"><span class="form-icon">↗</span><div><strong>${esc(tr('testPayoutTitle'))}</strong><small>${esc(tr('testPayoutHint'))}</small></div></div><div class="test-payout-warning">⚠ ${esc(tr('testPayoutWarning'))}</div><div class="settings-grid"><label class="settings-field"><span>${esc(tr('testPayoutAddress'))}</span><input id="adminTestPayoutAddress" class="text-input" maxlength="42" placeholder="0x…"></label><label class="settings-field"><span>${esc(tr('testPayoutAmount'))}</span><input id="adminTestPayoutAmount" class="text-input" type="number" min="1" step="0.01" inputmode="decimal" value="1.00"></label></div><label class="switch-row test-payout-ack"><span>${esc(tr('testPayoutAcknowledge'))}</span><input id="adminTestPayoutAck" type="checkbox"></label><button id="sendAdminTestPayout" class="primary-btn" type="button" ${enabled?'':'disabled'}>${esc(tr('testPayoutSend'))}</button>${enabled?'':`<p class="field-hint">${esc(tr('realPayoutsDisabled'))}</p>`}</article>
      <section class="admin-subsection"><div class="section-row"><h3>${esc(tr('testPayoutHistory'))}</h3></div><div class="stack-list">${rows}</div></section>`;
    if($('sendAdminTestPayout')) $('sendAdminTestPayout').addEventListener('click',createAdminTestPayout);
    $('admin-treasury').querySelectorAll('[data-test-payout-tx]').forEach((b)=>b.addEventListener('click',()=>openExternal(`${explorer}${b.dataset.testPayoutTx}`)));
  }
  async function createAdminTestPayout(){
    const address=$('adminTestPayoutAddress').value.trim(), raw=$('adminTestPayoutAmount').value.trim().replace(',','.'), amount=Number(raw);
    if(!/^0x[a-fA-F0-9]{40}$/.test(address)){toast(tr('invalidWallet'),'error');return;}
    if(!Number.isFinite(amount)||amount<1){toast(tr('testPayoutMinimum'),'error');return;}
    if(!$('adminTestPayoutAck').checked){toast(tr('testPayoutWarning'),'error');return;}
    const prompt=tr('testPayoutConfirmDialog').replace('{amount}',amount.toFixed(2)).replace('{address}',compactAddress(address));
    if(!window.confirm(prompt)) return;
    const btn=$('sendAdminTestPayout'); btn.disabled=true;
    const idem=(crypto.randomUUID?crypto.randomUUID():`test-${Date.now()}-${Math.random()}`).replace(/-/g,'');
    try{
      await api('/api/admin/treasury/test-payout',{method:'POST',headers:{'Idempotency-Key':idem},body:JSON.stringify({address,amount:raw,confirm:'REAL_PAYOUT'})});
      toast(tr('testPayoutQueued'),'success');
      setTimeout(()=>{ if(state.active==='admin'&&state.adminTab==='treasury') loadAdminTreasury().catch(()=>{}); },1200);
    }catch(e){handleApiError(e); if($('sendAdminTestPayout')) $('sendAdminTestPayout').disabled=false;}
  }
  const setupStatusText=(value)=>({
    bootstrap:tr('setupBootstrap'),
    configured:tr('setupConfigured'),
    active:tr('setupActive'),
    degraded:tr('setupDegraded')
  }[value]||value||tr('setupBootstrap'));
  async function loadAdminSystem(){
    const [s,cfgSafe]=await Promise.all([api('/api/admin/system'),api('/api/admin/chain-config')]);
    const cfg=s.blockchain_configuration||{},setup=cfgSafe.setup||s.setup||{},isOwner=Boolean(state.data&&state.data.auth&&state.data.auth.is_owner);
    state.adminCache.chainConfig=cfgSafe;
    if(!state.adminCache.pendingChainConfig && cfgSafe.pending) state.adminCache.pendingChainConfig=cfgSafe.pending;
    const taskRows=Object.entries(s.tasks||{}).map(([k,v])=>`<div class="system-state-row"><span>${esc(k)}</span><strong>${esc(v==='running'?tr('running'):tr('stopped'))}</strong></div>`).join('');
    const statusCard=`<article class="panel setup-state-card ${esc(setup.status||'bootstrap')}"><div><span>${esc(tr('setupState'))}</span><strong>${esc(setupStatusText(setup.status))}</strong></div><small>${esc(setup.financial_ready?'financial ready':tr('financialLocked'))}</small>${setup.public_fingerprint?`<code>${esc(tr('setupFingerprint'))}: ${esc(setup.public_fingerprint)}</code>`:''}</article>`;
    const modeOptions=[['production',tr('modeProduction')],['testnet',tr('modeTestnet')]].map(([value,label])=>`<option value="${value}" ${cfgSafe.mode===value?'selected':''}>${esc(label)}</option>`).join('');
    const pending=state.adminCache.pendingChainConfig;
    const activation=pending?`<article class="panel settings-card activation-card"><div class="form-heading"><span class="form-icon">✓</span><div><strong>${esc(tr('chainValidated'))}</strong><small>${esc(tr('activationWarning'))}</small></div></div><div class="treasury-confirm-value"><span>${esc(tr('treasury'))}</span><code>${esc(pending.treasury_address)}</code></div><p class="field-hint">${esc(tr('setupFingerprint'))}: ${esc(pending.public_fingerprint)}</p><label class="settings-field"><span>${esc(tr('treasuryConfirm'))}</span><input id="chainTreasuryConfirmation" class="text-input" autocomplete="off" placeholder="0x…"></label><label class="settings-field"><span>${esc(tr('chainActivationReason'))}</span><input id="chainActivationReason" class="text-input" maxlength="500" value="${esc(tr('chainReasonPlaceholder'))}"></label><button id="activateChainConfig" class="primary-btn danger-confirm" type="button">${esc(tr('activateChain'))}</button></article>`:'';
    const ownerForm=isOwner?`<article class="panel settings-card chain-settings-card"><div class="form-heading"><span class="form-icon">⛓</span><div><strong>${esc(tr('chainConfigTitle'))}</strong><small>${esc(tr('chainValidateHint'))}</small></div></div><div class="secret-status-grid"><div><span>RPC</span><strong>${esc(cfgSafe.rpc_configured?tr('secretConfigured'):tr('secretMissing'))}</strong></div><div><span>WSS</span><strong>${esc(cfgSafe.wss_configured?tr('secretConfigured'):tr('secretMissing'))}</strong></div><div><span>${esc(tr('signing'))}</span><strong>${esc(cfgSafe.seed_configured?tr('secretConfigured'):tr('secretMissing'))}</strong></div></div><label class="settings-field"><span>${esc(tr('chainMode'))}</span><select id="chainMode" class="select-input">${modeOptions}</select></label><div class="settings-grid chain-public-grid"><label class="settings-field"><span>${esc(tr('tokenContract'))}</span><input id="chainTokenContract" class="text-input" maxlength="42" value="${esc(cfgSafe.token_contract||'0x55d398326f99059fF775485246999027B3197955')}" placeholder="0x…"></label><label class="settings-field"><span>${esc(tr('scanStartBlock'))}</span><input id="chainScanStart" class="text-input" type="number" min="1" step="1" inputmode="numeric" value="${esc(cfgSafe.scan_start_block||'')}" placeholder="42000000"><small class="field-hint">${esc(tr('scanStartHint'))}</small></label></div><div class="secret-fields"><label class="settings-field"><span>${esc(tr('rpcEndpoint'))} · ${esc(tr('writeOnly'))}</span><input id="chainRpcUrl" class="text-input" type="password" autocomplete="off" spellcheck="false" placeholder="https://…"></label><label class="settings-field"><span>${esc(tr('wssEndpoint'))} · ${esc(tr('writeOnly'))}</span><input id="chainWssUrl" class="text-input" type="password" autocomplete="off" spellcheck="false" placeholder="wss://…"></label><label class="settings-field"><span>${esc(tr('seedPhraseWriteOnly'))} · ${esc(tr('writeOnly'))}</span><input id="chainSeedPhrase" class="text-input" type="password" autocomplete="off" spellcheck="false" placeholder="12 / 15 / 18 / 21 / 24 words"></label><p class="setup-risk">${esc(tr('seedWebviewWarning'))}</p><label class="switch-row"><span>${esc(tr('acceptSeedRisk'))}</span><input id="chainSeedRiskAck" type="checkbox"></label><label class="settings-field"><span>${esc(tr('chainReason'))}</span><input id="chainConfigReason" class="text-input" maxlength="500" value="${esc(tr('chainReasonPlaceholder'))}"></label></div><button id="validateChainConfig" class="primary-btn" type="button">${esc(tr('chainValidate'))}</button></article>`:`<article class="panel settings-card"><strong>${esc(tr('ownerRequired'))}</strong><p class="field-hint">${esc(tr('financialLocked'))}</p></article>`;
    const status=String(setup.status||'bootstrap');
    const stepsCard=`<article class="panel activation-steps-card" role="note"><div class="form-heading"><span class="form-icon">①</span><div><strong>${esc(tr('activationStepsTitle'))}</strong><small>${esc(tr('keyBackupHint'))}</small></div></div><ol class="activation-steps"><li class="${status==='bootstrap'&&!pending?'current':''}">${esc(tr('activationStep1'))}</li><li class="${pending?'current':''}">${esc(tr('activationStep2'))}</li><li class="${pending?'':''}">${esc(tr('activationStep3'))}</li><li>${esc(tr('activationStep4'))}</li></ol></article>`;
    const postActive=status==='active'?`<article class="panel post-activate-card"><div class="form-heading"><span class="form-icon">✓</span><div><strong>${esc(tr('postActivateChecklist'))}</strong><small>${esc(tr('postActivateTerms'))}</small></div></div><p class="field-hint">${esc(tr('postActivateBackup'))}</p><button id="goAdminTerms" class="secondary-btn touch-target" type="button">${esc(tr('terms'))}</button></article>`:'';
    $('admin-system').innerHTML=`${statusCard}${stepsCard}<div class="system-grid"><article class="panel system-card"><h3>${esc(tr('system'))}</h3><div class="system-state-row"><span>${esc(tr('uptime'))}</span><strong>${esc(Math.floor(Number(s.uptime_seconds||0)/60))} min</strong></div><div class="system-state-row"><span>Chain ID</span><strong>${esc(s.chain_id)}</strong></div><div class="system-state-row"><span>RPC</span><strong>${cfg.rpc_configured?esc(tr('configured')):esc(tr('notConfigured'))}</strong></div><div class="system-state-row"><span>WSS</span><strong>${cfg.wss_configured?esc(tr('configured')):esc(tr('notConfigured'))}</strong></div></article><article class="panel system-card"><h3>${esc(tr('workers'))}</h3>${taskRows||'—'}</article></div>${ownerForm}${activation}${postActive}`;
    if($('validateChainConfig'))$('validateChainConfig').addEventListener('click',validateAdminChainConfig);
    if($('activateChainConfig'))$('activateChainConfig').addEventListener('click',activateAdminChainConfig);
    if($('goAdminTerms'))$('goAdminTerms').addEventListener('click',()=>setAdminTab('terms'));
  }
  async function validateAdminChainConfig(){
    const token_contract=$('chainTokenContract').value.trim(),mode=$('chainMode').value,scan=Number($('chainScanStart').value),rpc=$('chainRpcUrl').value.trim(),wss=$('chainWssUrl').value.trim(),seed=$('chainSeedPhrase').value.trim(),reason=$('chainConfigReason').value.trim();
    if(!/^0x[a-fA-F0-9]{40}$/.test(token_contract)||!Number.isFinite(scan)||scan<0||!rpc||!wss||!seed||reason.length<4){toast(tr('secretFieldsRequired'),'error');return;}
    if(mode==='production' && scan<=0){toast(tr('scanBlockRequired'),'error');return;}
    if(!$('chainSeedRiskAck').checked){toast(tr('seedWebviewWarning'),'error');return;}
    const btn=$('validateChainConfig');btn.disabled=true;
    let payload={mode,token_contract,scan_start_block:Math.round(scan),rpc_url:rpc,wss_url:wss,seed_phrase:seed,reason};
    try{
      state.adminCache.pendingChainConfig=await api('/api/admin/chain-config/validate',{method:'POST',body:JSON.stringify(payload)});
      toast(tr('chainValidated'),'success');
      await loadAdminSystem();
    }catch(e){handleApiError(e);}
    finally{
      ['chainRpcUrl','chainWssUrl','chainSeedPhrase'].forEach((id)=>{if($(id))$(id).value='';});
      payload=null;
      if(btn&&document.body.contains(btn))btn.disabled=false;
    }
  }
  async function activateAdminChainConfig(){
    const pending=state.adminCache.pendingChainConfig,confirmation=$('chainTreasuryConfirmation').value.trim(),reason=$('chainActivationReason').value.trim();
    if(!pending){toast(tr('chainPendingLost'),'error');return;}
    if(confirmation.toLowerCase()!==String(pending.treasury_address||'').toLowerCase()||reason.length<4){toast(tr('treasuryConfirmMismatch'),'error');return;}
    if(!window.confirm(tr('activationWarning')))return;
    const btn=$('activateChainConfig');btn.disabled=true;
    const operation_id=(crypto.randomUUID?crypto.randomUUID():`activate-${Date.now()}-${Math.random()}`).replace(/-/g,'');
    try{
      await api('/api/admin/chain-config/activate',{method:'POST',body:JSON.stringify({generation:pending.generation,treasury_confirmation:confirmation,operation_id,reason,confirm:'ACTIVATE_CHAIN'})});
      state.adminCache.pendingChainConfig=null;
      toast(tr('chainActivated'),'success');
      setTimeout(()=>location.reload(),5000);
    }catch(e){btn.disabled=false;handleApiError(e);}
  }
  async function loadAdminLogs(){
    const rows=await api('/api/admin/audit?limit=150');
    $('adminLogsList').innerHTML=rows.length?rows.map((r)=>`<article class="list-card"><div class="list-card-header"><strong>${esc(r.event_type)}</strong><span class="date-text">${esc(fmtDate(r.created_at))}</span></div><div class="log-details">${esc(r.details||'—')}</div></article>`).join(''):`<div class="empty-state">${esc(tr('noLogs'))}</div>`;
  }

  function clearPollingTimers(){
    if(state.refreshTimer){clearInterval(state.refreshTimer);state.refreshTimer=null;}
    if(state.notificationTimer){clearInterval(state.notificationTimer);state.notificationTimer=null;}
  }
  function startPollingTimers(){
    clearPollingTimers();
    const bootstrapMs=document.visibilityState==='hidden'?120000:30000;
    const notifyMs=document.visibilityState==='hidden'?60000:15000;
    state.refreshTimer=setInterval(()=>{
      if(document.visibilityState==='hidden') return;
      refreshBootstrap();
    }, bootstrapMs);
    state.notificationTimer=setInterval(()=>{
      if(document.visibilityState==='hidden') return;
      loadNotifications({silent:true});
    }, notifyMs);
  }
  function restorePersistedInvoice(){
    try{
      const raw=sessionStorage.getItem('novera_active_invoice');
      if(!raw) return;
      const invoice=JSON.parse(raw);
      const expiresAt=Number(invoice&&invoice.expires_at||0);
      if(expiresAt && expiresAt < Math.floor(Date.now()/1000) - 3600){
        sessionStorage.removeItem('novera_active_invoice');
        return;
      }
      state.activeInvoice=invoice;
      renderInvoice(invoice);
    }catch(_){}
  }

  async function boot(){
    applyTranslations();
    await loadTelegramSession();
    syncTelegramContext();
    await exchangeBotLogin();
    restorePersistedInvoice();
    try{const data=verifyBootstrapIdentity(await captureAuthSession(await api('/api/bootstrap',{cache:'no-store'})));render(data);const view=qs.get('view');if(view==='admin'&&data.auth&&data.auth.is_admin)switchView('admin');else if(view&&document.getElementById(`view-${view}`))switchView(view);loadNotifications({silent:true});startPollingTimers();}catch(e){
      // An expired stored token may be repaired by current signed initData.
      if(e&&e.status===401&&state.telegramSessionToken){
        await clearTelegramSession(); syncTelegramContext();
        try{const data=verifyBootstrapIdentity(await captureAuthSession(await api('/api/bootstrap',{cache:'no-store'})));render(data);loadNotifications({silent:true});startPollingTimers();return;}catch(e2){e=e2;}
      }
      await handleApiError(e);$('heroSubtitle').textContent=apiErrorText(e&&e.detail,e&&e.status)||tr('authFailed');
    }
  }

  document.querySelectorAll('.nav-btn').forEach((b)=>b.addEventListener('click',()=>switchView(b.dataset.view,{push:true})));
  document.querySelectorAll('[data-go]').forEach((b)=>b.addEventListener('click',()=>switchView(b.dataset.go,{push:true})));
  document.querySelectorAll('[data-history]').forEach((b)=>b.addEventListener('click',()=>{state.historyFilter=b.dataset.history;document.querySelectorAll('[data-history]').forEach((x)=>x.classList.toggle('active',x===b));if(state.data)renderHistory(state.data.deposits||[],state.data.payouts||[],state.data.chain||{});}));
  document.querySelectorAll('[data-admin-user-filter]').forEach((b)=>b.addEventListener('click',()=>{state.adminUserFilter=b.dataset.adminUserFilter;document.querySelectorAll('[data-admin-user-filter]').forEach((x)=>x.classList.toggle('active',x===b));renderAdminUsersList();}));
  if($('sessionRecoverCta')) $('sessionRecoverCta').addEventListener('click',()=>{
    const support=state.data&&state.data.support_url;
    const chat=state.data&&state.data.chat_url;
    const target=support||chat;
    if(target){
      if(tg&&tg.openTelegramLink&&String(target).startsWith('https://t.me/')) tg.openTelegramLink(target);
      else window.open(target,'_blank','noopener');
    }
    toast(tr('sessionRecoverHint'),'info');
  });
  document.querySelectorAll('.admin-tab').forEach((b)=>b.addEventListener('click',()=>setAdminTab(b.dataset.adminTab)));
  document.querySelectorAll('[data-payout-filter]').forEach((b)=>b.addEventListener('click',()=>{state.payoutFilter=b.dataset.payoutFilter;document.querySelectorAll('[data-payout-filter]').forEach((x)=>x.classList.toggle('active',x===b));renderAdminPayoutRows();}));
  $('brandBtn').addEventListener('click',()=>switchView('home',{push:true}));$('profileBtn').addEventListener('click',()=>switchView('profile',{push:true}));$('notificationsBtn').addEventListener('click',()=>switchView('notifications',{push:true}));$('markAllNotificationsRead').addEventListener('click',markAllNotificationsRead);
  document.querySelectorAll('[data-notification-filter]').forEach((b)=>b.addEventListener('click',()=>{state.notificationFilter=b.dataset.notificationFilter;document.querySelectorAll('[data-notification-filter]').forEach((x)=>x.classList.toggle('active',x===b));renderNotifications({items:state.notifications,unread_count:state.notificationUnread});}));
  $('languageBtn').addEventListener('click',showLanguage);$('languageBackdrop').addEventListener('click',()=>$('languageSheet').classList.add('hidden'));$('languageClose').addEventListener('click',()=>$('languageSheet').classList.add('hidden'));
  $('userModalBackdrop').addEventListener('click',()=>$('userModal').classList.add('hidden'));$('userModalClose').addEventListener('click',()=>$('userModal').classList.add('hidden'));
  $('closeMiniApp').addEventListener('click',()=>{if(tg&&tg.close)tg.close();else location.reload();});
  if($('retryConnection')) $('retryConnection').addEventListener('click',async()=>{
    setOfflineBanner(false);
    const ok=await refreshBootstrap();
    if(ok){await loadNotifications({silent:true});toast(tr('online'),'success');}
  });
  window.addEventListener('offline',()=>setOfflineBanner(true));
  window.addEventListener('online',()=>{setOfflineBanner(false);refreshBootstrap().catch(()=>{});});
  if(typeof navigator!=='undefined' && navigator.onLine===false) setOfflineBanner(true);
  $('saveWallet').addEventListener('click',saveWallet);$('createDeposit').addEventListener('click',createDeposit);$('copyReferral').addEventListener('click',()=>copyText($('referralLink').textContent));$('refreshTeam').addEventListener('click',loadTeam);$('withdrawReferral').addEventListener('click',withdrawReferral);
  if($('walletInput')){
    $('walletInput').addEventListener('input',()=>{state.walletDirty=true;});
    $('walletInput').addEventListener('change',()=>{state.walletDirty=true;});
  }
  $('profitCalcAmount').addEventListener('input',updateProfitCalculator);$('calculatorToDeposit').addEventListener('click',calculatorToDeposit);
  const openExternal=(url)=>{if(!url)return;if(tg&&tg.openTelegramLink&&url.startsWith('https://t.me/'))tg.openTelegramLink(url);else window.open(url,'_blank','noopener');};
  $('openSupport').addEventListener('click',()=>openExternal(state.data&&state.data.support_url));
  $('openChat').addEventListener('click',()=>openExternal(state.data&&state.data.chat_url));
  $('profileWallet').addEventListener('click',()=>switchView('wallet',{push:true}));
  $('refreshAdmin').addEventListener('click',()=>loadAdmin(state.adminTab));$('adminSearchBtn').addEventListener('click',()=>loadAdminUsers($('adminSearch').value.trim()));$('adminSearch').addEventListener('keydown',(e)=>{if(e.key==='Enter')loadAdminUsers($('adminSearch').value.trim());});$('sendBroadcast').addEventListener('click',sendBroadcast);$('grantAdminBtn').addEventListener('click',addAdminAccess);$('adminGrantInput').addEventListener('keydown',(e)=>{if(e.key==='Enter')addAdminAccess();});
  document.querySelectorAll('[data-format-tag]').forEach((b)=>b.addEventListener('click',()=>wrapBroadcastSelection(b.dataset.formatTag)));
  $('broadcastLinkFormat').addEventListener('click',formatBroadcastLink);$('broadcastImage').addEventListener('change',selectBroadcastImage);$('removeBroadcastImage').addEventListener('click',clearBroadcastImage);$('addBroadcastButton').addEventListener('click',addBroadcastButton);renderBroadcastButtons();
  $('broadcastText').addEventListener('input',renderBroadcastPreview);
  $('broadcastAudience').addEventListener('change',renderBroadcastAudienceCount);
  $('testBroadcast').addEventListener('click',sendBroadcastTest);
  $('createPromoBtn').addEventListener('click',createPromo);
  $('createCampaignBtn').addEventListener('click',createCampaign);
  $('campaignScheduleMode').addEventListener('change',updateCampaignScheduleFields);
  $('campaignWeekdaysRow').addEventListener('click',(e)=>{const b=e.target.closest('[data-weekday]');if(b)b.classList.toggle('active');});
  updateCampaignScheduleFields();

  window.addEventListener('pageshow',refreshTelegramAccountContext);
  window.addEventListener('focus',refreshTelegramAccountContext);
  document.addEventListener('visibilitychange',()=>{
    startPollingTimers();
    if(document.visibilityState==='visible'){
      refreshTelegramAccountContext();
      refreshBootstrap();
    }
  });
  if(tg&&tg.onEvent){try{tg.onEvent('activated',refreshTelegramAccountContext);}catch(_){}}

  boot();
})();
