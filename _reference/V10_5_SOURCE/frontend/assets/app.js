(() => {
  'use strict';
  // GFORT V9.4 native account isolation

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  // GFORT V10 per-account Telegram SecureStorage authentication
  // GFORT V10.1 admin inviter management
  // GFORT V10.2 real admin treasury test payouts
  // GFORT V10.3 Telegram bot + in-app notification center
  const qs = new URLSearchParams(window.location.search);
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>'"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const money = (minor) => (Number(minor || 0) / 1000000).toFixed(2);
  const percent = (bps) => `${(Number(bps || 0) / 100).toFixed(Number(bps || 0) % 100 ? 1 : 0)}%`;
  const fmtDate = (ts) => ts ? new Date(Number(ts) * 1000).toLocaleString([], {day:'2-digit',month:'2-digit',year:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—';
  const compactAddress = (value) => value && value.length > 14 ? `${value.slice(0,8)}…${value.slice(-6)}` : (value || '—');
  const calcMoney = (value) => Number(value || 0).toLocaleString([], {minimumFractionDigits:2,maximumFractionDigits:2});

  const LANGS = [
    ['ru','RU','Русский','Русский'],['en','EN','English','English'],['uk','UA','Українська','Українська'],
    ['bg','BG','Български','Български'],['kk','KZ','Қазақша','Қазақша'],['be','BY','Беларуская','Беларуская'],
    ['es','ES','Español','Español'],['it','IT','Italiano','Italiano'],['tr','TR','Türkçe','Türkçe'],['tk','TM','Türkmençe','Türkmençe']
  ];

  const I18N = {
    ru: {
      sessionTitle:'Нужна авторизация Telegram',sessionText:'Для старой сессии после обновления один раз отправьте боту /start и откройте GFORT из нового сообщения. Дальше /start повторять не нужно.',close:'Закрыть',connecting:'Подключение',dashboard:'ЛИЧНЫЙ КАБИНЕТ',welcome:'Добро пожаловать',heroSubtitle:'Ваши активы, выплаты и команда в одном месте.',activeAssets:'Сейчас в работе',totalDeposited:'Всего пополнено',totalPaid:'Получено выплат',team:'Команда',people:'участников',partnerIncome:'Партнёрский доход',quickActions:'БЫСТРЫЕ ДЕЙСТВИЯ',manageFunds:'Управление',deposit:'Пополнить',bep20:'USDT · BEP-20',assets:'Активы',activeAndCompleted:'активные и завершённые',referrals:'Рефералы',fiveLevels:'5 уровней',history:'История',allOperations:'все операции',currentTerms:'ТЕКУЩИЕ УСЛОВИЯ',minimum:'Минимум',period:'Период',dailyRate:'Ставка/день',termsFineprint:'Фактические параметры отображаются из текущей конфигурации сервиса.',portfolio:'ПОРТФЕЛЬ',assetsDesc:'Активные и завершённые депозиты с прогрессом выплат.',wallet:'Кошелёк',depositAndPayout:'Пополнение и выплаты',walletDesc:'Адрес для выплат и создание точной заявки на пополнение USDT BEP-20.',payoutWallet:'Кошелёк для выплат',payoutWalletHint:'BNB Smart Chain · адрес 0x…',address:'Адрес',save:'Сохранить',newDeposit:'Новое пополнение',amount:'Сумма USDT',createInvoice:'Создать заявку',networkWarningTitle:'Проверьте сеть и точную сумму',networkWarningText:'Отправляйте только USDT BEP-20 на показанный адрес и ровно ту сумму, которую сформировала заявка.',partnerProgram:'ПАРТНЁРСКАЯ ПРОГРАММА',teamDesc:'Реферальная ссылка, пять уровней и фактическая статистика вашей структуры.',referralLink:'Ваша реферальная ссылка',copy:'Копировать',structure:'СТРУКТУРА',members:'Участники',activity:'АКТИВНОСТЬ',historyDesc:'Депозиты и выплаты в хронологическом порядке.',all:'Все',deposits:'Депозиты',payouts:'Выплаты',account:'АККАУНТ',profile:'Профиль',support:'Поддержка',adminPanel:'Админ-панель',adminDesc:'Пользователи, операции, рассылки и состояние системы.',overview:'Обзор',users:'Пользователи',broadcasts:'Рассылка',terms:'Условия',system:'Система',logs:'Логи',userSearch:'Поиск по ID или @username',search:'Найти',failed:'Ошибки',newBroadcast:'Новая рассылка',blockedExcluded:'Заблокированные пользователи исключаются автоматически',audience:'Аудитория',allUsers:'Все пользователи',investors:'Только инвесторы',partners:'Только партнёры',message:'Сообщение',send:'Отправить',home:'Главная',admin:'Админ',language:'Язык',user:'Пользователь',online:'Онлайн',blocked:'Заблокирован',active:'Активный',completed:'Завершён',paused:'Пауза',error:'Ошибка',pending:'Ожидает',paid:'Оплачен',expired:'Истёк',confirmed:'Подтверждён',queued:'В очереди',signed:'Подписан',broadcast:'Отправлен',daily:'Выплата',referral:'Реферальная',level:'Уровень',turnover:'Оборот',earned:'Получено',waiting:'Ожидает',personal:'Лично',line:'Линия',activeCount:'Активных',completedCount:'Завершённых',principal:'Сумма',progress:'Прогресс',days:'дней',noAssets:'Активов пока нет.',noHistory:'История операций пока пуста.',noMembers:'Участников в структуре пока нет.',walletSaved:'Кошелёк сохранён',invalidWallet:'Проверьте BSC-адрес',invoiceCreated:'Заявка создана',network:'Сеть',exactAmount:'Точная сумма',validUntil:'Действует до',copyAddress:'Адрес',copyAmount:'Сумма',copyAll:'Все реквизиты',copied:'Скопировано',copyFailed:'Не удалось скопировать',sessionExpired:'Сессия Telegram устарела',openFromTelegram:'Откройте GFORT через кнопку Mini App в Telegram.',authFailed:'Не удалось авторизоваться',role:'Роль',telegramId:'Telegram ID',registered:'Регистрация',payoutAddress:'Кошелёк выплат',referrer:'Пригласил',none:'—',adminRole:'Администратор',userRole:'Пользователь',refresh:'Обновить',newUsers:'Новых за сутки',active7d:'Активных 7 дней',activeDeposits:'Активных депозитов',failedPayouts:'Проблемных выплат',deposited:'Пополнено',paidOut:'Выплачено',today:'За сутки',netFlow:'Депозиты − подтвержд. выплаты',openDetails:'Открыть',block:'Заблокировать',unblock:'Разблокировать',transactions:'Транзакции',status:'Статус',attempts:'Попытки',retry:'Повторить',broadcastSent:'Рассылка создана',emptyMessage:'Введите сообщение',systemOnline:'Система работает',configured:'Настроено',notConfigured:'Не настроено',running:'Работает',stopped:'Остановлено',treasury:'Казна',confirmations:'Подтверждения',scanInterval:'Интервал сканирования',noLogs:'Событий пока нет.',noUsers:'Пользователи не найдены.',noDeposits:'Депозитов пока нет.',noPayouts:'Выплат пока нет.',notificationCenter:'ЦЕНТР СОБЫТИЙ',notifications:'Уведомления',notificationsDesc:'Пополнения, выплаты и события партнёрской программы.',markAllRead:'Прочитать все',partnerProgramShort:'Партнёрка',noNotifications:'Уведомлений пока нет.',newNotification:'Новое уведомление',telegramPushHint:'Сообщения бота работают как push-уведомления Telegram.'
    },
    en: {dashboard:'DASHBOARD',welcome:'Welcome',heroSubtitle:'Your assets, payouts and team in one place.',activeAssets:'Active now',totalDeposited:'Total deposited',totalPaid:'Total paid',team:'Team',people:'members',partnerIncome:'Partner income',quickActions:'QUICK ACTIONS',manageFunds:'Manage',deposit:'Deposit',assets:'Assets',referrals:'Referrals',history:'History',wallet:'Wallet',profile:'Profile',support:'Support',home:'Home',admin:'Admin',language:'Language',currentTerms:'CURRENT TERMS',minimum:'Minimum',period:'Period',dailyRate:'Rate/day',portfolio:'PORTFOLIO',assetsDesc:'Active and completed deposits with payout progress.',depositAndPayout:'Deposits & payouts',payoutWallet:'Payout wallet',address:'Address',save:'Save',newDeposit:'New deposit',amount:'USDT amount',createInvoice:'Create invoice',partnerProgram:'PARTNER PROGRAM',referralLink:'Your referral link',copy:'Copy',members:'Members',activity:'ACTIVITY',all:'All',deposits:'Deposits',payouts:'Payouts',account:'ACCOUNT',adminPanel:'Admin panel',overview:'Overview',users:'Users',broadcasts:'Broadcasts',terms:'Terms',system:'System',logs:'Logs',search:'Search',failed:'Failed',send:'Send',user:'User',online:'Online',connecting:'Connecting',sessionTitle:'Telegram authorization required',sessionText:'For an old session after this update, use /start once and open GFORT from the new message. You will not need /start again.',close:'Close',active:'Active',completed:'Completed',pending:'Pending',confirmed:'Confirmed',queued:'Queued',error:'Error',level:'Level',turnover:'Turnover',earned:'Earned',waiting:'Pending',personal:'Personal',line:'Line',activeCount:'Active',completedCount:'Completed',principal:'Amount',progress:'Progress',days:'days',noAssets:'No assets yet.',noHistory:'No activity yet.',noMembers:'No members yet.',walletSaved:'Wallet saved',invalidWallet:'Check the BSC address',invoiceCreated:'Invoice created',network:'Network',exactAmount:'Exact amount',validUntil:'Valid until',copyAddress:'Address',copyAmount:'Amount',copyAll:'Copy details',copied:'Copied',copyFailed:'Copy failed',sessionExpired:'Telegram session expired',openFromTelegram:'Open GFORT using the Mini App button in Telegram.',authFailed:'Authentication failed',role:'Role',telegramId:'Telegram ID',registered:'Registered',payoutAddress:'Payout wallet',referrer:'Referrer',adminRole:'Administrator',userRole:'User',refresh:'Refresh',newUsers:'New 24h',active7d:'Active 7d',activeDeposits:'Active deposits',failedPayouts:'Failed payouts',deposited:'Deposited',paidOut:'Paid',today:'24h',netFlow:'Deposits − confirmed payouts',openDetails:'Details',block:'Block',unblock:'Unblock',retry:'Retry',broadcastSent:'Broadcast created',emptyMessage:'Enter a message',systemOnline:'System online',configured:'Configured',notConfigured:'Not configured',running:'Running',stopped:'Stopped',treasury:'Treasury',confirmations:'Confirmations',scanInterval:'Scan interval',noLogs:'No events yet.',noUsers:'No users found.',noDeposits:'No deposits yet.',noPayouts:'No payouts yet.',notificationCenter:'EVENT CENTER',notifications:'Notifications',notificationsDesc:'Deposits, payouts and partner-program events.',markAllRead:'Mark all read',partnerProgramShort:'Partners',noNotifications:'No notifications yet.',newNotification:'New notification',telegramPushHint:'Bot messages work as Telegram push notifications.'},
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
    ru:{administrators:'Администраторы',adminManagement:'Управление администраторами',adminManagementHint:'Полный доступ к админ-панели и команде /admin.',adminIdentifier:'Telegram ID или @username',addAdmin:'Добавить',removeAdmin:'Убрать права',adminUserMustExist:'Пользователь должен хотя бы один раз открыть GFORT, чтобы появиться в базе.',protectedAdmin:'Основной администратор',fullAdmin:'Полные права',adminAdded:'Администратор добавлен',adminRemoved:'Права администратора удалены',userNotFound:'Пользователь не найден',invalidAdmin:'Проверьте Telegram ID или @username',cannotRemoveSelf:'Нельзя снять права администратора у самого себя',cannotRemoveOwner:'Основного администратора нельзя удалить',adminGrantNotFound:'Права администратора уже отсутствуют',accountBlocked:'Аккаунт заблокирован',adminAccessRequired:'Недостаточно прав администратора',tooManyRequests:'Слишком много запросов. Попробуйте немного позже.',requestTooLarge:'Слишком большой запрос',invalidData:'Проверьте введённые данные',depositsDisabled:'Пополнения временно недоступны',treasuryNotConfigured:'Кошелёк системы не настроен',requestFailed:'Не удалось выполнить запрос. Попробуйте ещё раз.',loginLinkExpired:'Ссылка входа устарела. Отправьте /start и откройте новую кнопку.',blockedNow:'Пользователь заблокирован',unblockedNow:'Пользователь разблокирован',payoutQueued:'Выплата поставлена в очередь',maximum:'Максимум',uptime:'Время работы',workers:'Фоновые процессы',signing:'Подпись транзакций',source:'Источник',addedBy:'Добавил',remove:'Удалить',bootstrapSource:'Основной',dynamicSource:'Добавлен',noAdmins:'Дополнительных администраторов пока нет.'},
    en:{administrators:'Administrators',adminManagement:'Administrator management',adminManagementHint:'Full access to the admin panel and /admin command.',adminIdentifier:'Telegram ID or @username',addAdmin:'Add',removeAdmin:'Remove access',adminUserMustExist:'The user must open GFORT at least once before they can be promoted.',protectedAdmin:'Primary administrator',fullAdmin:'Full access',adminAdded:'Administrator added',adminRemoved:'Administrator access removed',userNotFound:'User not found',invalidAdmin:'Check the Telegram ID or @username',cannotRemoveSelf:'You cannot remove your own administrator access',cannotRemoveOwner:'The primary administrator cannot be removed',adminGrantNotFound:'Administrator access is already absent',accountBlocked:'Account is blocked',adminAccessRequired:'Administrator access is required',tooManyRequests:'Too many requests. Please try again shortly.',requestTooLarge:'The request is too large',invalidData:'Check the entered data',depositsDisabled:'Deposits are temporarily unavailable',treasuryNotConfigured:'System wallet is not configured',requestFailed:'Request failed. Please try again.',loginLinkExpired:'The login link has expired. Send /start and use the new button.',blockedNow:'User blocked',unblockedNow:'User unblocked',payoutQueued:'Payout queued',maximum:'Maximum',uptime:'Uptime',workers:'Workers',signing:'Transaction signing',source:'Source',addedBy:'Added by',remove:'Remove',bootstrapSource:'Primary',dynamicSource:'Added',noAdmins:'No additional administrators yet.'},
    uk:{administrators:'Адміністратори',adminManagement:'Керування адміністраторами',adminManagementHint:'Повний доступ до адмін-панелі та команди /admin.',adminIdentifier:'Telegram ID або @username',addAdmin:'Додати',removeAdmin:'Зняти права',adminUserMustExist:'Користувач має хоча б один раз відкрити GFORT.',protectedAdmin:'Основний адміністратор',fullAdmin:'Повні права',adminAdded:'Адміністратора додано',adminRemoved:'Права адміністратора видалено',userNotFound:'Користувача не знайдено',invalidAdmin:'Перевірте Telegram ID або @username',cannotRemoveSelf:'Не можна зняти права адміністратора у себе',cannotRemoveOwner:'Основного адміністратора не можна видалити',adminGrantNotFound:'Права адміністратора вже відсутні',accountBlocked:'Акаунт заблоковано',adminAccessRequired:'Потрібні права адміністратора',tooManyRequests:'Забагато запитів. Спробуйте трохи пізніше.',requestTooLarge:'Запит завеликий',invalidData:'Перевірте введені дані',depositsDisabled:'Поповнення тимчасово недоступні',treasuryNotConfigured:'Системний гаманець не налаштовано',requestFailed:'Не вдалося виконати запит. Спробуйте ще раз.',loginLinkExpired:'Посилання входу застаріло. Надішліть /start і відкрийте нову кнопку.',blockedNow:'Користувача заблоковано',unblockedNow:'Користувача розблоковано',payoutQueued:'Виплату поставлено в чергу',maximum:'Максимум',uptime:'Час роботи',workers:'Фонові процеси',signing:'Підпис транзакцій',source:'Джерело',addedBy:'Додав',remove:'Видалити',bootstrapSource:'Основний',dynamicSource:'Доданий',noAdmins:'Додаткових адміністраторів поки немає.'},
    bg:{sessionTitle:'Сесията на Telegram е изтекла',sessionText:'Затворете Mini App и го отворете отново от бота.',close:'Затвори',sessionExpired:'Сесията на Telegram е изтекла',openFromTelegram:'Отворете GFORT чрез бутона Mini App в Telegram.',authFailed:'Неуспешно удостоверяване',walletSaved:'Портфейлът е запазен',invalidWallet:'Проверете BSC адреса',invoiceCreated:'Заявката е създадена',copied:'Копирано',copyFailed:'Неуспешно копиране',emptyMessage:'Въведете съобщение',broadcastSent:'Разпращането е създадено',payoutQueued:'Плащането е поставено на опашка',blockedNow:'Потребителят е блокиран',unblockedNow:'Потребителят е отблокиран',adminAdded:'Администраторът е добавен',adminRemoved:'Администраторските права са премахнати',userNotFound:'Потребителят не е намерен',requestFailed:'Заявката не бе изпълнена. Опитайте отново.',tooManyRequests:'Твърде много заявки. Опитайте малко по-късно.',accountBlocked:'Акаунтът е блокиран',administrators:'Администратори',addAdmin:'Добави',removeAdmin:'Премахни права'},
    kk:{sessionTitle:'Telegram сессиясының мерзімі аяқталды',sessionText:'Mini App-ты жауып, боттан қайта ашыңыз.',close:'Жабу',sessionExpired:'Telegram сессиясының мерзімі аяқталды',openFromTelegram:'GFORT-ты Telegram-дағы Mini App батырмасы арқылы ашыңыз.',authFailed:'Авторизация сәтсіз аяқталды',walletSaved:'Әмиян сақталды',invalidWallet:'BSC мекенжайын тексеріңіз',invoiceCreated:'Өтінім жасалды',copied:'Көшірілді',copyFailed:'Көшіру мүмкін болмады',emptyMessage:'Хабарлама енгізіңіз',broadcastSent:'Тарату жасалды',payoutQueued:'Төлем кезекке қойылды',blockedNow:'Пайдаланушы бұғатталды',unblockedNow:'Пайдаланушы бұғаттан шығарылды',adminAdded:'Әкімші қосылды',adminRemoved:'Әкімші құқықтары алынды',userNotFound:'Пайдаланушы табылмады',requestFailed:'Сұрауды орындау мүмкін болмады. Қайта көріңіз.',tooManyRequests:'Сұраулар тым көп. Сәл кейінірек қайталап көріңіз.',accountBlocked:'Аккаунт бұғатталған',administrators:'Әкімшілер',addAdmin:'Қосу',removeAdmin:'Құқықты алып тастау'},
    be:{sessionTitle:'Сесія Telegram скончылася',sessionText:'Закрыйце Mini App і адкрыйце яго зноў з бота.',close:'Закрыць',sessionExpired:'Сесія Telegram скончылася',openFromTelegram:'Адкрыйце GFORT праз кнопку Mini App у Telegram.',authFailed:'Не ўдалося аўтарызавацца',walletSaved:'Кашалёк захаваны',invalidWallet:'Праверце BSC-адрас',invoiceCreated:'Заяўка створана',copied:'Скапіравана',copyFailed:'Не ўдалося скапіяваць',emptyMessage:'Увядзіце паведамленне',broadcastSent:'Рассылка створана',payoutQueued:'Выплата пастаўлена ў чаргу',blockedNow:'Карыстальнік заблакаваны',unblockedNow:'Карыстальнік разблакаваны',adminAdded:'Адміністратар дададзены',adminRemoved:'Правы адміністратара выдалены',userNotFound:'Карыстальнік не знойдзены',requestFailed:'Не ўдалося выканаць запыт. Паспрабуйце яшчэ раз.',tooManyRequests:'Занадта шмат запытаў. Паспрабуйце пазней.',accountBlocked:'Акаўнт заблакаваны',administrators:'Адміністратары',addAdmin:'Дадаць',removeAdmin:'Зняць правы'},
    es:{sessionTitle:'La sesión de Telegram ha caducado',sessionText:'Cierra la Mini App y vuelve a abrirla desde el bot.',close:'Cerrar',sessionExpired:'La sesión de Telegram ha caducado',openFromTelegram:'Abre GFORT con el botón Mini App de Telegram.',authFailed:'No se pudo autenticar',walletSaved:'Cartera guardada',invalidWallet:'Comprueba la dirección BSC',invoiceCreated:'Solicitud creada',copied:'Copiado',copyFailed:'No se pudo copiar',emptyMessage:'Introduce un mensaje',broadcastSent:'Difusión creada',payoutQueued:'Pago puesto en cola',blockedNow:'Usuario bloqueado',unblockedNow:'Usuario desbloqueado',adminAdded:'Administrador añadido',adminRemoved:'Acceso de administrador eliminado',userNotFound:'Usuario no encontrado',requestFailed:'No se pudo completar la solicitud. Inténtalo de nuevo.',tooManyRequests:'Demasiadas solicitudes. Inténtalo de nuevo en breve.',accountBlocked:'La cuenta está bloqueada',administrators:'Administradores',addAdmin:'Añadir',removeAdmin:'Quitar acceso'},
    it:{sessionTitle:'La sessione Telegram è scaduta',sessionText:'Chiudi la Mini App e riaprila dal bot.',close:'Chiudi',sessionExpired:'La sessione Telegram è scaduta',openFromTelegram:'Apri GFORT con il pulsante Mini App in Telegram.',authFailed:'Autenticazione non riuscita',walletSaved:'Portafoglio salvato',invalidWallet:'Controlla l’indirizzo BSC',invoiceCreated:'Richiesta creata',copied:'Copiato',copyFailed:'Impossibile copiare',emptyMessage:'Inserisci un messaggio',broadcastSent:'Invio creato',payoutQueued:'Pagamento messo in coda',blockedNow:'Utente bloccato',unblockedNow:'Utente sbloccato',adminAdded:'Amministratore aggiunto',adminRemoved:'Accesso amministratore rimosso',userNotFound:'Utente non trovato',requestFailed:'Impossibile completare la richiesta. Riprova.',tooManyRequests:'Troppe richieste. Riprova tra poco.',accountBlocked:'Account bloccato',administrators:'Amministratori',addAdmin:'Aggiungi',removeAdmin:'Rimuovi accesso'},
    tr:{sessionTitle:'Telegram oturumu sona erdi',sessionText:'Mini App’i kapatın ve bottan tekrar açın.',close:'Kapat',sessionExpired:'Telegram oturumu sona erdi',openFromTelegram:'GFORT’u Telegram’daki Mini App düğmesinden açın.',authFailed:'Kimlik doğrulama başarısız',walletSaved:'Cüzdan kaydedildi',invalidWallet:'BSC adresini kontrol edin',invoiceCreated:'Talep oluşturuldu',copied:'Kopyalandı',copyFailed:'Kopyalanamadı',emptyMessage:'Bir mesaj girin',broadcastSent:'Yayın oluşturuldu',payoutQueued:'Ödeme kuyruğa alındı',blockedNow:'Kullanıcı engellendi',unblockedNow:'Kullanıcının engeli kaldırıldı',adminAdded:'Yönetici eklendi',adminRemoved:'Yönetici yetkisi kaldırıldı',userNotFound:'Kullanıcı bulunamadı',requestFailed:'İstek tamamlanamadı. Tekrar deneyin.',tooManyRequests:'Çok fazla istek. Kısa süre sonra tekrar deneyin.',accountBlocked:'Hesap engellendi',administrators:'Yöneticiler',addAdmin:'Ekle',removeAdmin:'Yetkiyi kaldır'},
    tk:{sessionTitle:'Telegram sessiýasynyň möhleti gutardy',sessionText:'Mini App-y ýapyň we botdan täzeden açyň.',close:'Ýap',sessionExpired:'Telegram sessiýasynyň möhleti gutardy',openFromTelegram:'GFORT-y Telegram-daky Mini App düwmesi arkaly açyň.',authFailed:'Tassyklama başartmady',walletSaved:'Gapjyk ýatda saklandy',invalidWallet:'BSC salgysyny barlaň',invoiceCreated:'Arza döredildi',copied:'Göçürildi',copyFailed:'Göçürip bolmady',emptyMessage:'Habar giriziň',broadcastSent:'Ugratma döredildi',payoutQueued:'Töleg nobata goýuldy',blockedNow:'Ulanyjy petiklendi',unblockedNow:'Ulanyjy açyldy',adminAdded:'Administrator goşuldy',adminRemoved:'Administrator hukuklary aýryldy',userNotFound:'Ulanyjy tapylmady',requestFailed:'Talaby ýerine ýetirip bolmady. Gaýtadan synanyşyň.',tooManyRequests:'Talaplar örän köp. Biraz soň gaýtadan synanyşyň.',accountBlocked:'Hasap petiklenen',administrators:'Administratorlar',addAdmin:'Goş',removeAdmin:'Hukugy aýyr'}
  };
  Object.entries(NOTICE_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

  const CONTROL_I18N = {
    ru:{accountBalance:'Баланс аккаунта',internalBalance:'Внутренний баланс',balanceReason:'Причина изменения',balanceReasonHint:'Причина обязательна и сохраняется в журнале действий.',setBalance:'Изменить баланс',balanceSaved:'Баланс пользователя изменён',walletUpdated:'Кошелёк пользователя изменён',walletManagement:'Кошелёк выплат',walletManagementHint:'Можно заменить или очистить адрес выплат пользователя.',clearWallet:'Очистить',balanceHistory:'История изменений баланса',noBalanceHistory:'Изменений баланса пока нет.',formatHint:'Выделите текст и примените форматирование. В Telegram отправляется безопасный HTML.',attachImage:'Прикрепить картинку',imageTooLarge:'Картинка должна быть не больше 5 МБ',imageType:'Поддерживаются только JPEG и PNG',broadcastButtons:'Кнопки',broadcastButtonsHint:'До 8 кнопок-ссылок под сообщением.',addButton:'+ Кнопка',buttonText:'Текст кнопки',buttonUrl:'Ссылка https://…',linkUrl:'Введите ссылку для выделенного текста',broadcastMediaFailed:'Не удалось загрузить картинку',broadcastRequiresContent:'Добавьте текст или картинку',settingsTitle:'Параметры проекта',settingsHint:'Изменения сохраняются в базе и применяются без переустановки.',saveSettings:'Сохранить параметры',settingsSaved:'Параметры сохранены',profitSettings:'Доходность и депозиты',operationsSettings:'Операционные настройки',referralSettings:'Партнёрские уровни',dailyRatePercent:'Ставка в день, %',payoutDays:'Количество дней выплат',depositMin:'Минимальный депозит, USDT',depositMax:'Максимальный депозит, USDT',invoiceTtl:'Срок заявки, минут',acceptDeposits:'Принимать новые депозиты',enablePayouts:'Разрешить выплаты',confirmationBlocksLabel:'Подтверждений блока',scanIntervalSeconds:'Интервал сканирования, сек.',supportUrl:'Ссылка поддержки',levelRate:'Ставка уровня, %',personalThreshold:'Личный депозит, USDT',lineThreshold:'Оборот линии, USDT',settingsPayoutDaysConflict:'Нельзя установить период ниже уже пройденного дня активного депозита.',invalidButton:'Проверьте текст и ссылку кнопки',imageAttached:'Картинка прикреплена',removeImage:'Убрать картинку',manualBalanceNote:'Это внутренний учётный баланс GFORT. Он хранится отдельно от on-chain депозитов и казны.',chainConfigTitle:'Blockchain и боевой режим',chainConfigHint:'RPC, WSS и seed-фраза не отображаются. Пустое поле сохраняет текущее значение.',chainMode:'Режим сети',modeProduction:'BSC Mainnet · боевой',modeTestnet:'BSC Testnet',modeOff:'Blockchain выключен',tokenContract:'Контракт токена',scanStartBlock:'Стартовый блок сканирования',treasuryDerived:'Кошелёк казны',rpcEndpoint:'Новый HTTPS RPC',wssEndpoint:'Новый приватный WSS',seedPhraseWriteOnly:'Новая seed-фраза',secretKeepHint:'Оставьте пустым, чтобы сохранить текущий секрет.',rpcCurrent:'Текущий RPC',wssCurrent:'Текущий WSS',seedCurrent:'Seed-фраза',secretConfigured:'настроена',secretMissing:'не настроена',saveRestart:'Сохранить и перезапустить',chainConfigSaved:'Blockchain-параметры сохранены. GFORT перезапускается…',chainHealthFailed:'Новые RPC/WSS не прошли проверку сети',seedInvalid:'Проверьте seed-фразу',invalidContract:'Проверьте адрес контракта токена',restartHint:'После сохранения контейнер автоматически перезапустится; повторная установка не нужна.',writeOnly:'только запись'},
    en:{accountBalance:'Account balance',internalBalance:'Internal balance',balanceReason:'Change reason',balanceReasonHint:'A reason is required and saved to the audit log.',setBalance:'Set balance',balanceSaved:'User balance updated',walletUpdated:'User wallet updated',walletManagement:'Payout wallet',walletManagementHint:'Replace or clear the user payout address.',clearWallet:'Clear',balanceHistory:'Balance change history',noBalanceHistory:'No balance changes yet.',formatHint:'Select text and apply formatting. Safe HTML is sent to Telegram.',attachImage:'Attach image',imageTooLarge:'Image must be 5 MB or smaller',imageType:'Only JPEG and PNG are supported',broadcastButtons:'Buttons',broadcastButtonsHint:'Up to 8 URL buttons under the message.',addButton:'+ Button',buttonText:'Button text',buttonUrl:'Link https://…',linkUrl:'Enter a link for the selected text',broadcastMediaFailed:'Could not upload image',broadcastRequiresContent:'Add text or an image',settingsTitle:'Project parameters',settingsHint:'Changes are saved in the database and applied without reinstalling.',saveSettings:'Save parameters',settingsSaved:'Parameters saved',profitSettings:'Yield and deposits',operationsSettings:'Operational settings',referralSettings:'Referral levels',dailyRatePercent:'Daily rate, %',payoutDays:'Payout days',depositMin:'Minimum deposit, USDT',depositMax:'Maximum deposit, USDT',invoiceTtl:'Invoice TTL, minutes',acceptDeposits:'Accept new deposits',enablePayouts:'Enable payouts',confirmationBlocksLabel:'Confirmation blocks',scanIntervalSeconds:'Scan interval, sec.',supportUrl:'Support URL',levelRate:'Level rate, %',personalThreshold:'Personal deposit, USDT',lineThreshold:'Line turnover, USDT',settingsPayoutDaysConflict:'Payout days cannot be below progress already reached by an active deposit.',invalidButton:'Check the button text and URL',imageAttached:'Image attached',removeImage:'Remove image',manualBalanceNote:'This is the internal GFORT account balance. It is stored separately from on-chain deposits and treasury.',chainConfigTitle:'Blockchain and live mode',chainConfigHint:'RPC, WSS and seed phrase are never displayed. Leave a field blank to keep its current value.',chainMode:'Network mode',modeProduction:'BSC Mainnet · live',modeTestnet:'BSC Testnet',modeOff:'Blockchain disabled',tokenContract:'Token contract',scanStartBlock:'Scan start block',treasuryDerived:'Treasury wallet',rpcEndpoint:'New HTTPS RPC',wssEndpoint:'New private WSS',seedPhraseWriteOnly:'New seed phrase',secretKeepHint:'Leave blank to keep the current secret.',rpcCurrent:'Current RPC',wssCurrent:'Current WSS',seedCurrent:'Seed phrase',secretConfigured:'configured',secretMissing:'not configured',saveRestart:'Save and restart',chainConfigSaved:'Blockchain settings saved. GFORT is restarting…',chainHealthFailed:'The new RPC/WSS endpoints failed network validation',seedInvalid:'Check the seed phrase',invalidContract:'Check the token contract address',restartHint:'The container restarts automatically after saving; reinstall is not required.',writeOnly:'write only'}
  };
  Object.entries(CONTROL_I18N).forEach(([code, values]) => Object.assign(I18N[code] || (I18N[code] = {}), values));

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
    ru:{links:'Ссылки',linksSettings:'Ссылки профиля',linksSettingsHint:'Здесь меняются кнопки «Поддержка» и «Чат» в профиле пользователя.',supportLink:'Ссылка поддержки',chatLink:'Ссылка на чат',saveLinks:'Сохранить ссылки',linksSaved:'Ссылки сохранены',openLink:'Открыть',invalidUrl:'Укажите корректную ссылку http(s):// или tg://',profitCalculator:'Калькулятор прибыли',profitCalculatorHint:'Расчёт по текущей ставке и сроку GFORT.',investmentAmount:'Сумма депозита',dailyProfit:'Прибыль в день',termProfit:'Прибыль за срок',depositReturn:'Возврат депозита',totalReturn:'Всего к получению',finalDayPayment:'Выплата в последний день',profitCalcNote:'Ежедневно выплачивается прибыль. В последний день отдельно возвращается тело депозита.',goToDeposit:'Перейти к пополнению',depositRange:'Допустимая сумма'},
    en:{links:'Links',linksSettings:'Profile links',linksSettingsHint:'Change the Support and Chat buttons shown in the user profile.',supportLink:'Support link',chatLink:'Chat link',saveLinks:'Save links',linksSaved:'Links saved',openLink:'Open',invalidUrl:'Enter a valid http(s):// or tg:// URL',profitCalculator:'Profit calculator',profitCalculatorHint:'Calculated from the current GFORT rate and term.',investmentAmount:'Deposit amount',dailyProfit:'Daily profit',termProfit:'Profit for the term',depositReturn:'Principal return',totalReturn:'Total to receive',finalDayPayment:'Final-day payout',profitCalcNote:'Profit is paid daily. The principal is returned separately on the final day.',goToDeposit:'Go to deposit',depositRange:'Allowed amount'},
    uk:{links:'Посилання',linksSettings:'Посилання профілю',linksSettingsHint:'Тут змінюються кнопки «Підтримка» і «Чат» у профілі користувача.',supportLink:'Посилання підтримки',chatLink:'Посилання на чат',saveLinks:'Зберегти посилання',linksSaved:'Посилання збережено',openLink:'Відкрити',invalidUrl:'Вкажіть коректне посилання http(s):// або tg://',profitCalculator:'Калькулятор прибутку',profitCalculatorHint:'Розрахунок за поточною ставкою та строком GFORT.',investmentAmount:'Сума депозиту',dailyProfit:'Прибуток на день',termProfit:'Прибуток за строк',depositReturn:'Повернення депозиту',totalReturn:'Всього до отримання',finalDayPayment:'Виплата в останній день',profitCalcNote:'Прибуток виплачується щодня. В останній день окремо повертається тіло депозиту.',goToDeposit:'Перейти до поповнення',depositRange:'Допустима сума'},
    bg:{links:'Връзки',linksSettings:'Връзки в профила',linksSettingsHint:'Тук се променят бутоните „Поддръжка“ и „Чат“ в профила.',supportLink:'Линк за поддръжка',chatLink:'Линк към чата',saveLinks:'Запази връзките',linksSaved:'Връзките са запазени',openLink:'Отвори',invalidUrl:'Въведете валиден http(s):// или tg:// адрес',profitCalculator:'Калкулатор на печалбата',profitCalculatorHint:'Изчисление по текущата ставка и срок на GFORT.',investmentAmount:'Сума на депозита',dailyProfit:'Печалба на ден',termProfit:'Печалба за срока',depositReturn:'Връщане на депозита',totalReturn:'Общо за получаване',finalDayPayment:'Плащане в последния ден',profitCalcNote:'Печалбата се изплаща ежедневно. В последния ден главницата се връща отделно.',goToDeposit:'Към депозит',depositRange:'Допустима сума'},
    kk:{links:'Сілтемелер',linksSettings:'Профиль сілтемелері',linksSettingsHint:'Мұнда профильдегі «Қолдау» және «Чат» батырмаларының сілтемелері өзгереді.',supportLink:'Қолдау сілтемесі',chatLink:'Чат сілтемесі',saveLinks:'Сілтемелерді сақтау',linksSaved:'Сілтемелер сақталды',openLink:'Ашу',invalidUrl:'Дұрыс http(s):// немесе tg:// сілтемесін енгізіңіз',profitCalculator:'Пайда калькуляторы',profitCalculatorHint:'GFORT ағымдағы мөлшерлемесі мен мерзімі бойынша есеп.',investmentAmount:'Депозит сомасы',dailyProfit:'Күндік пайда',termProfit:'Мерзімдегі пайда',depositReturn:'Депозитті қайтару',totalReturn:'Жалпы алынатын сома',finalDayPayment:'Соңғы күнгі төлем',profitCalcNote:'Пайда күн сайын төленеді. Соңғы күні депозит сомасы бөлек қайтарылады.',goToDeposit:'Толтыруға өту',depositRange:'Рұқсат етілген сома'},
    be:{links:'Спасылкі',linksSettings:'Спасылкі профілю',linksSettingsHint:'Тут змяняюцца кнопкі «Падтрымка» і «Чат» у профілі.',supportLink:'Спасылка падтрымкі',chatLink:'Спасылка на чат',saveLinks:'Захаваць спасылкі',linksSaved:'Спасылкі захаваны',openLink:'Адкрыць',invalidUrl:'Укажыце карэктную спасылку http(s):// або tg://',profitCalculator:'Калькулятар прыбытку',profitCalculatorHint:'Разлік па бягучай стаўцы і тэрміне GFORT.',investmentAmount:'Сума дэпазіту',dailyProfit:'Прыбытак у дзень',termProfit:'Прыбытак за тэрмін',depositReturn:'Вяртанне дэпазіту',totalReturn:'Усяго да атрымання',finalDayPayment:'Выплата ў апошні дзень',profitCalcNote:'Прыбытак выплачваецца штодня. У апошні дзень асобна вяртаецца сума дэпазіту.',goToDeposit:'Перайсці да папаўнення',depositRange:'Дапушчальная сума'},
    es:{links:'Enlaces',linksSettings:'Enlaces del perfil',linksSettingsHint:'Aquí se cambian los botones Soporte y Chat del perfil.',supportLink:'Enlace de soporte',chatLink:'Enlace del chat',saveLinks:'Guardar enlaces',linksSaved:'Enlaces guardados',openLink:'Abrir',invalidUrl:'Introduce una URL válida http(s):// o tg://',profitCalculator:'Calculadora de ganancias',profitCalculatorHint:'Cálculo según la tasa y el plazo actuales de GFORT.',investmentAmount:'Importe del depósito',dailyProfit:'Ganancia diaria',termProfit:'Ganancia del período',depositReturn:'Devolución del depósito',totalReturn:'Total a recibir',finalDayPayment:'Pago del último día',profitCalcNote:'La ganancia se paga diariamente. El capital se devuelve por separado el último día.',goToDeposit:'Ir al depósito',depositRange:'Importe permitido'},
    it:{links:'Link',linksSettings:'Link del profilo',linksSettingsHint:'Qui si cambiano i pulsanti Supporto e Chat del profilo.',supportLink:'Link supporto',chatLink:'Link chat',saveLinks:'Salva link',linksSaved:'Link salvati',openLink:'Apri',invalidUrl:'Inserisci un URL valido http(s):// o tg://',profitCalculator:'Calcolatore profitto',profitCalculatorHint:'Calcolo basato sul tasso e sulla durata attuali di GFORT.',investmentAmount:'Importo deposito',dailyProfit:'Profitto giornaliero',termProfit:'Profitto del periodo',depositReturn:'Rimborso deposito',totalReturn:'Totale da ricevere',finalDayPayment:'Pagamento dell’ultimo giorno',profitCalcNote:'Il profitto viene pagato ogni giorno. Il capitale viene restituito separatamente l’ultimo giorno.',goToDeposit:'Vai al deposito',depositRange:'Importo consentito'},
    tr:{links:'Bağlantılar',linksSettings:'Profil bağlantıları',linksSettingsHint:'Profildeki Destek ve Sohbet düğmelerinin bağlantıları burada değiştirilir.',supportLink:'Destek bağlantısı',chatLink:'Sohbet bağlantısı',saveLinks:'Bağlantıları kaydet',linksSaved:'Bağlantılar kaydedildi',openLink:'Aç',invalidUrl:'Geçerli bir http(s):// veya tg:// bağlantısı girin',profitCalculator:'Kâr hesaplayıcı',profitCalculatorHint:'GFORT’un mevcut oranı ve süresine göre hesaplama.',investmentAmount:'Yatırım tutarı',dailyProfit:'Günlük kâr',termProfit:'Dönem kârı',depositReturn:'Ana para iadesi',totalReturn:'Toplam alınacak',finalDayPayment:'Son gün ödemesi',profitCalcNote:'Kâr günlük ödenir. Ana para son gün ayrıca iade edilir.',goToDeposit:'Yatırıma geç',depositRange:'İzin verilen tutar'},
    tk:{links:'Salgylamalar',linksSettings:'Profil salgylamalary',linksSettingsHint:'Profildäki Goldaw we Çat düwmeleriniň salgylamalary şu ýerde üýtgedilýär.',supportLink:'Goldaw salgysy',chatLink:'Çat salgysy',saveLinks:'Salgylamalary ýazdyr',linksSaved:'Salgylamalar ýazdyryldy',openLink:'Aç',invalidUrl:'Dogry http(s):// ýa-da tg:// salgysyny giriziň',profitCalculator:'Peýda kalkulýatory',profitCalculatorHint:'GFORT häzirki göterimi we möhleti boýunça hasaplama.',investmentAmount:'Depozit möçberi',dailyProfit:'Günlük peýda',termProfit:'Möhlet peýdasy',depositReturn:'Depoziti gaýtarmak',totalReturn:'Jemi alynjak',finalDayPayment:'Soňky gün tölegi',profitCalcNote:'Peýda her gün tölenýär. Soňky gün depozitiň esasy möçberi aýratyn gaýtarylýar.',goToDeposit:'Depozite geç',depositRange:'Rugsat edilen möçber'}
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

  const normalizeLanguage = (code) => {
    const raw = String(code || '').toLowerCase().replace('_','-').split('-')[0];
    return LANGS.some((x) => x[0] === raw) ? raw : 'ru';
  };
  const telegramLang = tg && tg.initDataUnsafe && tg.initDataUnsafe.user ? tg.initDataUnsafe.user.language_code : '';
  const GFORT_SESSION_KEY = 'gfort_auth_session_v10';
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
    lang:normalizeLanguage(localStorage.getItem('gfort_lang') || localStorage.getItem('delta_lang') || telegramLang),
    active:'home', historyFilter:'all', adminTab:qs.get('tab') || 'overview', payoutFilter:'all', adminCache:{}, refreshTimer:null,
    broadcastImageFile:null, broadcastImageUrl:'', broadcastButtons:[], accountRefreshBusy:false,
    notifications:[], notificationUnread:0, notificationFilter:'all', notificationLastId:0, notificationTimer:null
  };

  const loadTelegramSession = async (force=false) => {
    if (!isNativeTelegramContext()) {
      state.telegramSessionToken=''; state.telegramSessionLoaded=true; return '';
    }
    if (state.telegramSessionLoaded && !force) return state.telegramSessionToken;
    let token='';
    if (tg && tg.SecureStorage && (!tg.isVersionAtLeast || tg.isVersionAtLeast('9.0'))) {
      token=await storageGet(tg.SecureStorage,GFORT_SESSION_KEY);
    }
    if (!token && tg && tg.CloudStorage && (!tg.isVersionAtLeast || tg.isVersionAtLeast('6.9'))) {
      token=await storageGet(tg.CloudStorage,GFORT_SESSION_KEY);
      if (token && tg.SecureStorage && (!tg.isVersionAtLeast || tg.isVersionAtLeast('9.0'))) {
        storageSet(tg.SecureStorage,GFORT_SESSION_KEY,token).catch(()=>{});
      }
    }
    state.telegramSessionToken=token;
    state.telegramSessionLoaded=true;
    state.telegramUserId=sessionUserId(token) || currentTelegramUserId();
    return token;
  };
  const saveTelegramSession = async (token) => {
    const clean=String(token||'');
    if (!clean || !isNativeTelegramContext()) return false;
    state.telegramSessionToken=clean;
    state.telegramSessionLoaded=true;
    state.telegramUserId=sessionUserId(clean) || currentTelegramUserId();
    const tasks=[];
    if (tg && tg.SecureStorage && (!tg.isVersionAtLeast || tg.isVersionAtLeast('9.0'))) tasks.push(storageSet(tg.SecureStorage,GFORT_SESSION_KEY,clean));
    if (tg && tg.CloudStorage && (!tg.isVersionAtLeast || tg.isVersionAtLeast('6.9'))) tasks.push(storageSet(tg.CloudStorage,GFORT_SESSION_KEY,clean));
    if (tasks.length) await Promise.allSettled(tasks);
    return true;
  };
  const clearTelegramSession = async () => {
    state.telegramSessionToken=''; state.telegramSessionLoaded=true;
    const tasks=[];
    if (tg && tg.SecureStorage) tasks.push(storageRemove(tg.SecureStorage,GFORT_SESSION_KEY));
    if (tg && tg.CloudStorage) tasks.push(storageRemove(tg.CloudStorage,GFORT_SESSION_KEY));
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
    const expected = sessionUserId(state.telegramSessionToken) || currentTelegramUserId();
    const actual = Number(data && data.auth ? data.auth.telegram_id : 0);
    if (expected && actual && expected !== actual) {
      const error = new Error('Telegram account context mismatch');
      error.status = 409;
      error.detail = 'Telegram account context mismatch';
      throw error;
    }
    return data;
  };


  const tr = (key) => (I18N[state.lang] && I18N[state.lang][key]) || (state.lang === 'ru' ? I18N.ru[key] : I18N.en[key]) || I18N.ru[key] || key;
  const toast = (text, type='info') => { const el=$('toast'); el.textContent=text; el.className=`toast ${type} show`; clearTimeout(toast._t); toast._t=setTimeout(()=>{el.className='toast';},2800); };
  const statusText = (value) => {
    const map = {active:'active',completed:'completed',paused:'paused',failed:'failed',pending:'pending',paid:'paid',expired:'expired',confirmed:'confirmed',queued:'queued',signed:'signed',broadcast:'broadcast'};
    return tr(map[value] || value || 'none');
  };
  const apiErrorText = (detail, status=0) => {
    const d=String(detail || '');
    const low=d.toLowerCase();
    if (low.includes('bot login link is invalid or expired')) return tr('loginLinkExpired');
    if (low.includes('initdata has expired') || low.includes('session has expired')) return tr('sessionExpired');
    if (low.includes('initdata is missing') || low.includes('session is missing')) return tr('openFromTelegram');
    if (low.includes('account is blocked')) return tr('accountBlocked');
    if (low.includes('admin access required')) return tr('adminAccessRequired');
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
    if (low.includes('set a payout wallet before withdrawing referral rewards')) return tr('setPayoutWalletFirst');
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
    if (status===422) return tr('invalidData');
    if (status===401) return tr('sessionExpired');
    return tr('requestFailed');
  };

  if (tg) {
    tg.ready(); tg.expand();
    try { tg.setHeaderColor('#08090c'); tg.setBackgroundColor('#08090c'); } catch (_) {}
    const syncHeight = () => document.documentElement.style.setProperty('--tg-height', `${tg.viewportStableHeight || window.innerHeight}px`);
    syncHeight(); if (tg.onEvent) tg.onEvent('viewportChanged', syncHeight);
  }

  async function api(path, options={}) {
    const headers = new Headers(options.headers || {});
    const initData = syncTelegramContext();
    if (state.telegramSessionToken) headers.set('X-GFORT-Session', state.telegramSessionToken);
    else headers.delete('X-GFORT-Session');
    if (initData) headers.set('X-Telegram-Init-Data', initData);
    else headers.delete('X-Telegram-Init-Data');
    if (isNativeTelegramContext()) headers.set('X-GFORT-Telegram-Context', '1');
    headers.set('X-Request-Id', (crypto.randomUUID ? crypto.randomUUID() : `req-${Date.now()}-${Math.random()}`).replace(/-/g,''));
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type','application/json');
    const res = await fetch(path, {...options, headers, credentials:'same-origin'});
    let body=null; try{body=await res.json();}catch(_){body=null;}
    if (!res.ok) {
      const err=new Error(apiErrorText(body && body.detail ? body.detail : '', res.status));
      err.status=res.status; err.detail=body && body.detail ? body.detail : '';
      throw err;
    }
    return body;
  }


  async function exchangeBotLogin() {
    if (!state.loginToken) return false;
    const token = state.loginToken;
    const headers = new Headers({
      'Content-Type':'application/json',
      'X-Request-Id':(crypto.randomUUID ? crypto.randomUUID() : `req-${Date.now()}-login`).replace(/-/g,'')
    });
    const initData = syncTelegramContext();
    if (state.telegramSessionToken) headers.set('X-GFORT-Session', state.telegramSessionToken);
    if (initData) headers.set('X-Telegram-Init-Data', initData);
    if (isNativeTelegramContext()) headers.set('X-GFORT-Telegram-Context', '1');
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
    if (state.active==='admin' && state.data && state.data.auth && state.data.auth.is_admin) loadAdminTab(state.adminTab);
  }

  function renderLanguageList() {
    $('languageList').innerHTML=LANGS.map(([code,short,name,native])=>`<button class="language-option ${code===state.lang?'active':''}" type="button" data-language="${code}"><span><strong>${esc(native)}</strong><small>${esc(name)} · ${esc(short)}</small></span><span class="language-check">${code===state.lang?'✓':''}</span></button>`).join('');
    $('languageList').querySelectorAll('[data-language]').forEach((b)=>b.addEventListener('click',()=>setLanguage(b.dataset.language)));
  }
  function setLanguage(code){ state.lang=normalizeLanguage(code); localStorage.setItem('gfort_lang',state.lang); $('languageSheet').classList.add('hidden'); applyTranslations(); }
  function showLanguage(){ $('languageSheet').classList.remove('hidden'); renderLanguageList(); }

  function switchView(name, {push=false}={}) {
    state.active=name;
    document.querySelectorAll('.view').forEach((v)=>v.classList.toggle('active',v.id===`view-${name}`));
    document.querySelectorAll('.nav-btn').forEach((b)=>b.classList.toggle('active',b.dataset.view===name));
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
    const name=auth.first_name||user.first_name||'GFORT';
    state.notificationUnread=Number(data.notification_unread_count||state.notificationUnread||0);
    updateNotificationBadge();

    $('accountState').textContent=tr('online');
    $('networkState').textContent=chain.enabled ? `BSC ${chain.chain_id||''} · ${chain.token_symbol||'USDT'}` : 'WEB';
    $('heroName').textContent=name; $('heroName').classList.toggle('long-name',Array.from(String(name)).length>12);
    $('activePrincipal').textContent=money(activeMinor);
    if ($('accountBalance')) $('accountBalance').textContent=money(user.manual_balance_minor);
    $('totalDeposited').textContent=money(depositedMinor);
    $('totalPaid').textContent=money(paidMinor);
    $('teamCount').textContent=team.count||0;
    $('refIncome').textContent=money(team.referral_earned_minor);
    $('termMin').textContent=`${terms.deposit_min_usdt||0} USDT`;
    $('termDays').textContent=`${terms.payout_days||0} ${tr('days')}`;
    $('termRate').textContent=percent(terms.daily_profit_bps);
    $('termsHeadline').textContent=`${percent(terms.daily_profit_bps)} · ${terms.payout_days||0} ${tr('days')}`;
    renderProfitCalculator(terms);
    $('walletInput').value=user.payout_address||'';
    $('walletState').textContent=user.payout_address ? compactAddress(user.payout_address) : '';
    $('referralLink').textContent=data.referral_link||'—';

    $('profileName').textContent=name;
    $('profileUsername').textContent=auth.username?`@${auth.username}`:`ID ${auth.telegram_id||user.telegram_id||'—'}`;
    $('profileAvatar').textContent=(name[0]||'G').toUpperCase(); $('profileBtn').textContent=(name[0]||'G').toUpperCase();
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
    $('assetsSummary').innerHTML=[
      [tr('activeCount'),active.length],[tr('activeAssets'),`${money(activeMinor)} USDT`],[tr('completedCount'),completed.length]
    ].map(([k,v])=>`<div class="summary-mini"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');
    $('assetList').innerHTML=deposits.length?deposits.map((d)=>{
      const totalDays=Number(terms.payout_days||20), paidDays=Number(d.paid_days||0), progress=Math.max(0,Math.min(100,(paidDays/Math.max(1,totalDays))*100));
      return `<article class="list-card"><div class="list-card-header"><div><strong>${money(d.principal_minor)} USDT</strong><small>#${esc(d.id)} · ${fmtDate(d.opened_at)}</small></div><span class="tag ${esc(d.status)}">${esc(statusText(d.status))}</span></div><progress class="asset-progress" max="100" value="${progress.toFixed(1)}"></progress><small>${esc(tr('progress'))}: ${paidDays}/${totalDays} ${esc(tr('days'))}</small></article>`;
    }).join(''):`<div class="empty-state">${esc(tr('noAssets'))}</div>`;
  }

  function renderHistory(deposits,payouts,chain) {
    const events=[];
    deposits.forEach((x)=>events.push({type:'deposits',title:tr('deposit'),status:x.status,amount:money(x.principal_minor),ts:x.opened_at,id:x.id}));
    payouts.forEach((x)=>events.push({type:'payouts',title:x.subtype==='principal'?tr('principalReturn'):(x.kind==='referral'?tr('referral'):tr('daily')),status:x.status,amount:money(x.amount_minor),ts:x.created_at,id:x.id,tx:x.tx_hash}));
    events.sort((a,b)=>Number(b.ts)-Number(a.ts));
    const filtered=state.historyFilter==='all'?events:events.filter((x)=>x.type===state.historyFilter);
    $('historyList').innerHTML=filtered.length?filtered.map((e)=>`<article class="list-card"><div class="list-card-header"><div><strong>${esc(e.title)}</strong><small>#${esc(e.id)} · ${esc(fmtDate(e.ts))}</small></div><div><strong class="${e.type==='payouts'?'amount-positive':''}">${e.type==='payouts'?'+':''}${esc(e.amount)} USDT</strong><small>${esc(statusText(e.status))}</small></div></div>${e.tx&&chain.explorer_tx_url?`<a class="tx-link" href="${esc(chain.explorer_tx_url.replace('{tx_hash}',e.tx))}" target="_blank" rel="noopener">${esc(compactAddress(e.tx))}</a>`:''}</article>`).join(''):`<div class="empty-state">${esc(tr('noHistory'))}</div>`;
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
    $('notificationList').innerHTML=filtered.length?filtered.map((n)=>`<article class="list-card notification-card ${n.read_at?'':'unread'}" data-notification-id="${esc(n.id)}"><div class="notification-icon ${esc(n.category||'system')}">${esc(notificationIcon(n.category,n.event_type))}</div><div class="notification-copy"><div class="list-card-header"><strong>${esc(n.title||tr('notifications'))}</strong><span class="date-text">${esc(fmtDate(n.created_at))}</span></div><p>${esc(n.body||'')}</p></div></article>`).join(''):`<div class="empty-state">${esc(tr('noNotifications'))}</div>`;
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
    }catch(e){if(!silent&&e.status!==401)handleApiError(e);}
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
    const minWithdrawal=Number(stats.minimum_withdrawal_minor||1000000);
    if($('withdrawReferral')){
      $('withdrawReferral').disabled=Number(stats.available_minor||0)<minWithdrawal || !(state.data&&state.data.chain&&state.data.chain.payouts_enabled);
      $('withdrawReferral').dataset.available=String(Number(stats.available_minor||0));
      $('withdrawReferral').dataset.minimum=String(minWithdrawal);
    }
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

  async function copyText(text){ try{await navigator.clipboard.writeText(String(text));toast(tr('copied'),'success');}catch(_){toast(tr('copyFailed'),'error');} }

  async function saveWallet(){
    const address=$('walletInput').value.trim(); if(!/^0x[a-fA-F0-9]{40}$/.test(address)){toast(tr('invalidWallet'),'error');return;}
    try{await api('/api/wallet',{method:'POST',body:JSON.stringify({address})});toast(tr('walletSaved'),'success');await refreshBootstrap();}catch(e){handleApiError(e);}
  }
  async function createDeposit(){
    const amount=Number($('depositAmount').value), terms=(state.data&&state.data.terms)||{};
    if(!Number.isFinite(amount)||amount<Number(terms.deposit_min_usdt||1)||amount>Number(terms.deposit_max_usdt||100000)){toast(`${tr('amount')}: ${terms.deposit_min_usdt||1}–${terms.deposit_max_usdt||100000} USDT`,'error');return;}
    try{
      const key=`invoice-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const invoice=await api('/api/deposits/invoice',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({amount})});
      renderInvoice(invoice);toast(tr('invoiceCreated'),'success');
    }catch(e){handleApiError(e);}
  }
  function renderInvoice(invoice){
    const exp=fmtDate(invoice.expires_at); const address=invoice.treasury_address, amount=`${invoice.exact_amount} USDT`;
    $('invoiceBox').classList.remove('hidden');
    $('invoiceBox').innerHTML=`<div class="invoice-line"><span>${esc(tr('network'))}</span><strong>BNB Smart Chain · BEP-20</strong></div><div class="invoice-line"><span>${esc(tr('exactAmount'))}</span><strong>${esc(amount)}</strong></div><div class="invoice-line"><span>${esc(tr('address'))}</span><strong>${esc(address)}</strong></div><div class="invoice-line"><span>${esc(tr('validUntil'))}</span><strong>${esc(exp)}</strong></div><div class="invoice-actions"><button type="button" data-copy-invoice="address">${esc(tr('copyAddress'))}</button><button type="button" data-copy-invoice="amount">${esc(tr('copyAmount'))}</button><button type="button" data-copy-invoice="all">${esc(tr('copyAll'))}</button></div>`;
    $('invoiceBox').querySelectorAll('[data-copy-invoice]').forEach((b)=>b.addEventListener('click',()=>{const mode=b.dataset.copyInvoice;copyText(mode==='address'?address:mode==='amount'?amount:`BNB Smart Chain (BEP-20)\n${address}\n${amount}`);}));
  }

  function showSessionError(){ $('sessionBanner').classList.remove('hidden'); $('accountState').textContent=tr('error'); }
  function handleApiError(e){ console.debug('GFORT API error',e&&e.status,e&&e.detail); if(e.status===401){showSessionError();} toast(apiErrorText(e&&e.detail,e&&e.status),'error'); }
  async function refreshBootstrap(){
    try{const data=verifyBootstrapIdentity(await captureAuthSession(await api('/api/bootstrap',{cache:'no-store'})));$('sessionBanner').classList.add('hidden');render(data,{preserve:true});}catch(e){handleApiError(e);}
  }
  async function refreshTelegramAccountContext(){
    if (state.accountRefreshBusy) return;
    state.accountRefreshBusy=true;
    try {
      const previousToken=String(state.telegramSessionToken||'');
      const previousUserId=sessionUserId(previousToken) || Number(state.telegramUserId||0);
      await loadTelegramSession(true);
      syncTelegramContext();
      const currentToken=String(state.telegramSessionToken||'');
      const currentUserId=sessionUserId(currentToken) || Number(state.telegramUserId||0);
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
      if (currentUserId && renderedUserId && currentUserId !== renderedUserId) {
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
    try{const summary=await api('/api/admin/summary');state.adminCache.summary=summary;renderAdminSummary(summary);if(tab==='overview')renderAdminOverview(summary);}catch(e){handleApiError(e);}
  }
  function renderAdminSummary(s){
    const items=[[tr('users'),s.users,tr('newUsers')+`: +${s.new_users_24h||0}`],[tr('active7d'),s.active_users_7d,tr('investors')+`: ${s.investors||0}`],[tr('activeDeposits'),s.active_deposits,`${money(s.active_principal_minor)} USDT`],[tr('failedPayouts'),s.failed_payouts,`${money(s.queued_minor)} USDT ${tr('waiting').toLowerCase()}`]];
    $('adminSummary').innerHTML=items.map(([k,v,sub])=>`<article class="admin-metric"><span>${esc(k)}</span><strong>${esc(v||0)}</strong><small>${esc(sub)}</small></article>`).join('');
  }
  function renderAdminOverview(s){
    const net=Number(s.deposited_minor||0)-Number(s.paid_minor||0);
    $('admin-overview').innerHTML=`<div class="overview-grid"><article class="panel overview-card"><h3>${esc(tr('deposited'))}</h3><div class="detail-row"><span>${esc(tr('deposited'))}</span><strong>${money(s.deposited_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('today'))}</span><strong>${money(s.deposits_24h_minor)} USDT</strong></div></article><article class="panel overview-card"><h3>${esc(tr('paidOut'))}</h3><div class="detail-row"><span>${esc(tr('paidOut'))}</span><strong>${money(s.paid_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('today'))}</span><strong>${money(s.payouts_24h_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('partnerIncome'))}</span><strong>${money(s.referral_paid_minor)} USDT</strong></div></article><article class="panel overview-card"><h3>${esc(tr('netFlow'))}</h3><p>${money(net)} USDT</p></article></div>`;
  }
  async function loadAdminTab(tab){
    if(!state.data||!state.data.auth||!state.data.auth.is_admin)return;
    try{
      if(tab==='users')await loadAdminUsers($('adminSearch').value.trim());
      else if(tab==='deposits')await loadAdminDeposits();
      else if(tab==='payouts')await loadAdminPayouts();
      else if(tab==='broadcasts')await loadAdminBroadcasts();
      else if(tab==='admins')await loadAdminAdmins();
      else if(tab==='terms')await loadAdminTerms();
      else if(tab==='links')await loadAdminLinks();
      else if(tab==='treasury')await loadAdminTreasury();
      else if(tab==='system')await loadAdminSystem();
      else if(tab==='logs')await loadAdminLogs();
      else if(tab==='overview'&&state.adminCache.summary)renderAdminOverview(state.adminCache.summary);
    }catch(e){handleApiError(e);}
  }
  async function loadAdminUsers(query=''){
    const users=await api(`/api/admin/users?query=${encodeURIComponent(query)}`);state.adminCache.users=users;
    $('adminUsersList').innerHTML=users.length?users.map((u)=>`<article class="list-card"><button class="admin-user-btn" type="button" data-user-id="${esc(u.telegram_id)}"><div class="list-card-header"><div><strong>${esc(u.first_name||u.username||u.telegram_id)}</strong><small>${u.username?'@'+esc(u.username)+' · ':''}ID ${esc(u.telegram_id)} · ${esc(fmtDate(u.created_at))}</small></div><div><strong>${money(u.manual_balance_minor)} USDT</strong><small>${esc(tr('accountBalance'))} · ${esc(u.deposit_count||0)} ${esc(tr('deposits').toLowerCase())}</small></div></div></button></article>`).join(''):`<div class="empty-state">${esc(tr('noUsers'))}</div>`;
    $('adminUsersList').querySelectorAll('[data-user-id]').forEach((b)=>b.addEventListener('click',()=>openAdminUser(b.dataset.userId)));
  }
  async function openAdminUser(id){
    try{const d=await api(`/api/admin/users/${encodeURIComponent(id)}`);renderAdminUserModal(d);$('userModal').classList.remove('hidden');}catch(e){handleApiError(e);}
  }
  function renderAdminUserModal(d){
    const u=d.user||{}, stats=d.stats||{}, ref=d.referrer, adjustments=d.balance_adjustments||[], referrerAdjustments=d.referrer_adjustments||[]; const name=u.first_name||u.username||u.telegram_id;
    const adjustmentRows=adjustments.length?adjustments.slice(0,12).map((x)=>`<div class="balance-audit-row"><div><strong>${money(x.new_balance_minor)} USDT</strong><small>${esc(fmtDate(x.created_at))} · ${Number(x.delta_minor||0)>=0?'+':''}${money(x.delta_minor)} USDT</small></div><span>${esc(x.reason||'—')}</span></div>`).join(''):`<div class="empty-state compact">${esc(tr('noBalanceHistory'))}</div>`;
    const refLabel=(item)=>item?(item.username?`@${item.username} · ID ${item.telegram_id}`:`${item.first_name||'ID'} ${item.first_name?'· ':''}ID ${item.telegram_id}`):tr('none');
    const refHistory=referrerAdjustments.length?referrerAdjustments.slice(0,10).map((x)=>{
      const oldRef=x.old_referrer_id?{telegram_id:x.old_referrer_id,username:x.old_referrer_username,first_name:x.old_referrer_first_name}:null;
      const newRef=x.new_referrer_id?{telegram_id:x.new_referrer_id,username:x.new_referrer_username,first_name:x.new_referrer_first_name}:null;
      return `<div class="balance-audit-row"><div><strong>${esc(refLabel(newRef))}</strong><small>${esc(fmtDate(x.created_at))}</small></div><span>${esc(tr('from'))}: ${esc(refLabel(oldRef))}</span></div>`;
    }).join(''):`<div class="empty-state compact">${esc(tr('noInviterHistory'))}</div>`;
    $('adminUserDetail').innerHTML=`<div class="user-detail-head"><div class="profile-avatar">${esc(String(name)[0]||'U')}</div><div><strong>${esc(name)}</strong><span>${u.username?'@'+esc(u.username)+' · ':''}ID ${esc(u.telegram_id)}</span></div></div>
      <div class="modal-section"><div class="detail-row"><span>${esc(tr('registered'))}</span><strong>${esc(fmtDate(u.created_at))}</strong></div><div class="detail-row"><span>${esc(tr('status'))}</span><strong>${u.blocked?esc(tr('blocked')):esc(tr('online'))}</strong></div><div class="detail-row"><span>${esc(tr('referrer'))}</span><strong>${esc(refLabel(ref))}</strong></div></div>
      <div class="modal-section user-control-section"><h4>${esc(tr('inviterManagement'))}</h4><div class="detail-row"><span>${esc(tr('currentInviter'))}</span><strong>${esc(refLabel(ref))}</strong></div><p class="field-hint">${esc(tr('inviterChangeHint'))}</p><label class="input-label" for="adminReferrerInput">${esc(tr('newInviter'))}</label><input id="adminReferrerInput" class="text-input" maxlength="64" autocomplete="off" value="${esc(ref?(ref.username?'@'+ref.username:String(ref.telegram_id)):'')}" placeholder="${esc(tr('inviterIdentifier'))}"><div class="admin-actions"><button id="saveAdminReferrer" class="admin-action" type="button">${esc(tr('setInviter'))}</button><button id="clearAdminReferrer" class="admin-action danger" type="button">${esc(tr('clearInviter'))}</button></div></div>
      <div class="modal-section user-control-section"><h4>${esc(tr('internalBalance'))}</h4><div class="big-balance">${money(u.manual_balance_minor)} <small>USDT</small></div><p class="field-hint">${esc(tr('manualBalanceNote'))}</p><label class="input-label" for="adminBalanceInput">${esc(tr('internalBalance'))}, USDT</label><input id="adminBalanceInput" class="text-input" type="number" min="0" step="0.000001" inputmode="decimal" value="${esc((Number(u.manual_balance_minor||0)/1000000).toFixed(6))}"><label class="input-label" for="adminBalanceReason">${esc(tr('balanceReason'))}</label><textarea id="adminBalanceReason" class="textarea-input compact-textarea" maxlength="500" rows="2" placeholder="${esc(tr('balanceReasonHint'))}"></textarea><button id="saveAdminBalance" class="primary-btn compact-primary" type="button">${esc(tr('setBalance'))}</button></div>
      <div class="modal-section user-control-section"><h4>${esc(tr('walletManagement'))}</h4><p class="field-hint">${esc(tr('walletManagementHint'))}</p><input id="adminWalletInput" class="text-input" maxlength="42" value="${esc(u.payout_address||'')}" placeholder="0x…"><div class="admin-actions"><button id="saveAdminWallet" class="admin-action" type="button">${esc(tr('save'))}</button><button id="clearAdminWallet" class="admin-action danger" type="button">${esc(tr('clearWallet'))}</button></div></div>
      <div class="modal-section"><div class="detail-row"><span>${esc(tr('deposited'))}</span><strong>${money(stats.deposited_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('activeAssets'))}</span><strong>${money(stats.active_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('paidOut'))}</span><strong>${money(stats.paid_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('partnerIncome'))}</span><strong>${money(stats.referral_paid_minor)} USDT</strong></div><div class="detail-row"><span>${esc(tr('team'))}</span><strong>${esc((d.partners||[]).length)}</strong></div></div>
      <div class="modal-section"><h4>${esc(tr('inviterHistory'))}</h4><div class="balance-audit-list">${refHistory}</div></div>
      <div class="modal-section"><h4>${esc(tr('balanceHistory'))}</h4><div class="balance-audit-list">${adjustmentRows}</div></div>
      <div class="admin-actions"><button id="toggleUserBlock" class="admin-action ${u.blocked?'success':'danger'}" type="button">${esc(u.blocked?tr('unblock'):tr('block'))}</button></div>`;
    $('toggleUserBlock').addEventListener('click',()=>toggleAdminUserBlock(u.telegram_id,!Boolean(u.blocked)));
    $('saveAdminBalance').addEventListener('click',()=>setAdminUserBalance(u.telegram_id));
    $('saveAdminWallet').addEventListener('click',()=>setAdminUserWallet(u.telegram_id,$('adminWalletInput').value.trim()));
    $('clearAdminWallet').addEventListener('click',()=>setAdminUserWallet(u.telegram_id,''));
    $('saveAdminReferrer').addEventListener('click',()=>setAdminUserReferrer(u.telegram_id,$('adminReferrerInput').value.trim()));
    $('clearAdminReferrer').addEventListener('click',()=>setAdminUserReferrer(u.telegram_id,''));
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
    try{await api(`/api/admin/users/${encodeURIComponent(id)}/balance`,{method:'POST',body:JSON.stringify({balance_usdt:raw,reason})});toast(tr('balanceSaved'),'success');await loadAdminUsers($('adminSearch').value.trim());await openAdminUser(id);}catch(e){handleApiError(e);}
  }
  async function setAdminUserWallet(id,address){
    try{await api(`/api/admin/users/${encodeURIComponent(id)}/wallet`,{method:'POST',body:JSON.stringify({address:address||null})});toast(tr('walletUpdated'),'success');await openAdminUser(id);}catch(e){handleApiError(e);}
  }
  async function toggleAdminUserBlock(id,blocked){
    try{await api(`/api/admin/users/${id}/block`,{method:'POST',body:JSON.stringify({blocked})});toast(blocked?tr('blockedNow'):tr('unblockedNow'),'success');await loadAdminUsers($('adminSearch').value.trim());await openAdminUser(id);}catch(e){handleApiError(e);}
  }
  async function loadAdminDeposits(){
    const rows=await api('/api/admin/deposits');
    $('adminDepositsList').innerHTML=rows.length?rows.map((d)=>`<article class="list-card"><div class="list-card-header"><div><strong>${money(d.principal_minor)} USDT</strong><small>${esc(d.first_name||d.username||d.user_id)} · ID ${esc(d.user_id)} · #${esc(d.id)}</small></div><span class="tag ${esc(d.status)}">${esc(statusText(d.status))}</span></div><small>${esc(fmtDate(d.opened_at))}${d.tx_hash?' · '+esc(compactAddress(d.tx_hash)):''}</small></article>`).join(''):`<div class="empty-state">${esc(tr('noDeposits'))}</div>`;
  }
  async function loadAdminPayouts(){
    const rows=await api('/api/admin/operations');state.adminCache.payouts=rows;renderAdminPayoutRows();
  }
  function renderAdminPayoutRows(){
    const rows=(state.adminCache.payouts||[]).filter((p)=>state.payoutFilter==='all'||p.status==='failed');
    $('adminPayoutsList').innerHTML=rows.length?rows.map((p)=>`<article class="list-card"><div class="list-card-header"><div><strong>${money(p.amount_minor)} USDT</strong><small>${esc(p.first_name||p.username||p.user_id)} · ${esc(p.admin_test?tr('testPayout'):(p.subtype==='principal'?tr('principalReturn'):(p.kind==='referral'?tr('referral'):tr('daily'))))} · #${esc(p.id)}</small></div><span class="tag ${esc(p.status)}">${esc(statusText(p.status))}</span></div><small>${esc(fmtDate(p.created_at))}${p.last_error?' · '+esc(p.last_error):''}</small>${p.status==='failed'?`<div class="admin-actions"><button class="admin-action" data-retry-payout="${esc(p.id)}" type="button">${esc(tr('retry'))}</button></div>`:''}</article>`).join(''):`<div class="empty-state">${esc(tr('noPayouts'))}</div>`;
    $('adminPayoutsList').querySelectorAll('[data-retry-payout]').forEach((b)=>b.addEventListener('click',()=>retryPayout(b.dataset.retryPayout)));
  }
  async function retryPayout(id){try{await api(`/api/admin/payouts/${id}/retry`,{method:'POST'});toast(tr('payoutQueued'),'success');await loadAdminPayouts();}catch(e){handleApiError(e);}}
  async function loadAdminBroadcasts(){
    const rows=await api('/api/admin/broadcasts');
    $('adminBroadcastList').innerHTML=rows.length?rows.map((b)=>{let buttons=[];try{buttons=JSON.parse(b.buttons_json||'[]')}catch(_){buttons=[]}const extras=[b.media_path?'▣ 1':'',buttons.length?`⌁ ${buttons.length}`:''].filter(Boolean).join(' · ');return `<article class="list-card"><div class="list-card-header"><div><strong>#${esc(b.id)} · ${esc(b.audience)}</strong><small>${esc(fmtDate(b.created_at))}${extras?' · '+esc(extras):''}</small></div><span class="tag ${esc(b.status)}">${esc(statusText(b.status))}</span></div><small class="broadcast-preview-text">${esc(b.message||'')}</small><div class="broadcast-progress"><span>✓ ${esc(b.delivered_count||0)}</span><span>× ${esc(b.failed_count||0)}</span><span>Σ ${esc(b.total_count||0)}</span></div></article>`}).join(''):'';
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
  }
  function selectBroadcastImage(){
    const file=$('broadcastImage').files&&$('broadcastImage').files[0];if(!file){clearBroadcastImage();return;}
    if(!['image/jpeg','image/png'].includes(file.type)){toast(tr('imageType'),'error');clearBroadcastImage();return;}
    if(file.size>5*1024*1024){toast(tr('imageTooLarge'),'error');clearBroadcastImage();return;}
    clearBroadcastImage();state.broadcastImageFile=file;state.broadcastImageUrl=URL.createObjectURL(file);$('broadcastImageThumb').src=state.broadcastImageUrl;$('broadcastImageName').textContent=file.name;$('broadcastImageSize').textContent=`${(file.size/1024/1024).toFixed(2)} MB`;$('broadcastImagePreview').classList.remove('hidden');
  }
  function renderBroadcastButtons(){
    const root=$('broadcastButtonsBuilder');
    root.innerHTML=state.broadcastButtons.map((item,index)=>`<div class="broadcast-button-row" data-button-index="${index}"><input class="text-input" data-button-text="${index}" maxlength="64" placeholder="${esc(tr('buttonText'))}" value="${esc(item.text||'')}"><input class="text-input" data-button-url="${index}" maxlength="2048" placeholder="${esc(tr('buttonUrl'))}" value="${esc(item.url||'')}"><button class="icon-btn small danger" type="button" data-remove-broadcast-button="${index}" aria-label="${esc(tr('remove'))}">×</button></div>`).join('');
    root.querySelectorAll('[data-button-text]').forEach((el)=>el.addEventListener('input',()=>{state.broadcastButtons[Number(el.dataset.buttonText)].text=el.value;}));
    root.querySelectorAll('[data-button-url]').forEach((el)=>el.addEventListener('input',()=>{state.broadcastButtons[Number(el.dataset.buttonUrl)].url=el.value;}));
    root.querySelectorAll('[data-remove-broadcast-button]').forEach((el)=>el.addEventListener('click',()=>{state.broadcastButtons.splice(Number(el.dataset.removeBroadcastButton),1);renderBroadcastButtons();}));
    if($('addBroadcastButton'))$('addBroadcastButton').disabled=state.broadcastButtons.length>=8;
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
    const btn=$('sendBroadcast');btn.disabled=true;
    try{const media_id=await uploadBroadcastImage();await api('/api/admin/broadcasts',{method:'POST',body:JSON.stringify({message,audience,media_id,buttons})});$('broadcastText').value='';state.broadcastButtons=[];renderBroadcastButtons();clearBroadcastImage();toast(tr('broadcastSent'),'success');await loadAdminBroadcasts();}catch(e){handleApiError(e);}finally{btn.disabled=false;}
  }
  async function loadAdminAdmins(){
    const rows=await api('/api/admin/admins');
    state.adminCache.admins=rows;
    $('adminAdminsList').innerHTML=rows.length?rows.map((a)=>{
      const name=a.first_name||a.username||a.telegram_id;
      const source=a.protected?tr('bootstrapSource'):tr('dynamicSource');
      const removeButton=!a.protected && Number(a.telegram_id)!==Number(state.data&&state.data.auth&&state.data.auth.telegram_id)
        ? `<button class="admin-action danger" type="button" data-remove-admin="${esc(a.telegram_id)}">${esc(tr('removeAdmin'))}</button>`:'';
      return `<article class="list-card"><div class="list-card-header"><div><strong>${esc(name)}</strong><small>${a.username?'@'+esc(a.username)+' · ':''}ID ${esc(a.telegram_id)}</small></div><span class="admin-source ${a.protected?'protected':'dynamic'}">${esc(source)}</span></div><div class="admin-badge-row"><span class="admin-source dynamic">${esc(tr('fullAdmin'))}</span>${a.granted_at?`<span class="date-text">${esc(fmtDate(a.granted_at))}</span>`:''}</div>${removeButton?`<div class="admin-actions">${removeButton}</div>`:''}</article>`;
    }).join(''):`<div class="empty-state">${esc(tr('noAdmins'))}</div>`;
    $('adminAdminsList').querySelectorAll('[data-remove-admin]').forEach((b)=>b.addEventListener('click',()=>removeAdminAccess(b.dataset.removeAdmin)));
  }
  async function addAdminAccess(){
    const identifier=$('adminGrantInput').value.trim();
    if(!identifier){toast(tr('invalidAdmin'),'error');return;}
    try{
      await api('/api/admin/admins',{method:'POST',body:JSON.stringify({identifier})});
      $('adminGrantInput').value='';
      toast(tr('adminAdded'),'success');
      await loadAdminAdmins();
    }catch(e){handleApiError(e);}
  }
  async function removeAdminAccess(id){
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
    $('saveRuntimeSettings').addEventListener('click',saveAdminSettings);
  }
  function numberValue(id){const value=Number($(id).value);if(!Number.isFinite(value))throw new Error('invalid');return value;}
  async function saveAdminSettings(){
    let payload;
    try{
      payload={daily_profit_bps:Math.round(numberValue('settingDailyRate')*100),payout_days:Math.round(numberValue('settingPayoutDays')),deposit_min_usdt:Math.round(numberValue('settingDepositMin')),deposit_max_usdt:Math.round(numberValue('settingDepositMax')),invoice_ttl_minutes:Math.round(numberValue('settingInvoiceTtl')),referral_level_bps:Array.from({length:5},(_,i)=>Math.round(numberValue(`settingLevelRate${i}`)*100)),referral_personal_thresholds_usdt:Array.from({length:5},(_,i)=>Math.round(numberValue(`settingPersonal${i}`))),referral_line_thresholds_usdt:Array.from({length:5},(_,i)=>Math.round(numberValue(`settingLine${i}`))),deposits_enabled:$('settingDepositsEnabled').checked,payouts_enabled:$('settingPayoutsEnabled').checked,confirmation_blocks:Math.round(numberValue('settingConfirmations')),deposit_scan_interval_seconds:Math.round(numberValue('settingScanInterval')),support_url:$('settingSupportUrl').value.trim(),chat_url:$('settingChatUrl').value.trim()};
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
      payouts_enabled:Boolean(current.payouts_enabled),
      confirmation_blocks:Number(current.confirmation_blocks||0),
      deposit_scan_interval_seconds:Number(current.deposit_scan_interval_seconds||0),
      support_url:String(current.support_url||''),
      chat_url:String(current.chat_url||'')
    },overrides);
  }
  async function loadAdminLinks(){
    const x=await api('/api/admin/settings');
    state.adminCache.settings=x;
    $('admin-links').innerHTML=`<article class="panel settings-card links-settings-card"><div class="form-heading"><span class="form-icon">↗</span><div><strong>${esc(tr('linksSettings'))}</strong><small>${esc(tr('linksSettingsHint'))}</small></div></div><div class="links-editor"><label class="settings-field"><span>${esc(tr('supportLink'))}</span><div class="link-edit-row"><input id="adminSupportLink" class="text-input" type="url" value="${esc(x.support_url||'')}" placeholder="https://t.me/..."><button id="previewSupportLink" class="compact-btn" type="button">${esc(tr('openLink'))}</button></div></label><label class="settings-field"><span>${esc(tr('chatLink'))}</span><div class="link-edit-row"><input id="adminChatLink" class="text-input" type="url" value="${esc(x.chat_url||'')}" placeholder="https://t.me/..."><button id="previewChatLink" class="compact-btn" type="button">${esc(tr('openLink'))}</button></div></label></div><div class="links-preview"><span>${esc(tr('profile'))}</span><div><button type="button" class="secondary-btn preview-only">? ${esc(tr('support'))}</button><button type="button" class="secondary-btn preview-only">✦ ${esc(tr('chat'))}</button></div></div><button id="saveProfileLinks" class="primary-btn" type="button">${esc(tr('saveLinks'))}</button></article>`;
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
  async function loadAdminSystem(){
    const [s,cfgSafe]=await Promise.all([api('/api/admin/system'),api('/api/admin/chain-config')]), cfg=s.blockchain_configuration||{};
    state.adminCache.chainConfig=cfgSafe;
    const taskRows=Object.entries(s.tasks||{}).map(([k,v])=>`<div class="system-state-row"><span>${esc(k)}</span><strong>${esc(v==='running'?tr('running'):tr('stopped'))}</strong></div>`).join('');
    const modeOptions=[['production',tr('modeProduction')],['testnet',tr('modeTestnet')],['off',tr('modeOff')]].map(([value,label])=>`<option value="${value}" ${cfgSafe.mode===value?'selected':''}>${esc(label)}</option>`).join('');
    $('admin-system').innerHTML=`<div class="system-grid"><article class="panel system-card"><h3>${esc(tr('system'))}</h3><div class="system-state-row"><span>${esc(tr('uptime'))}</span><strong>${esc(Math.floor(Number(s.uptime_seconds||0)/60))} min</strong></div><div class="system-state-row"><span>Chain ID</span><strong>${esc(s.chain_id)}</strong></div><div class="system-state-row"><span>RPC</span><strong>${cfg.rpc_configured?esc(tr('configured')):esc(tr('notConfigured'))}</strong></div><div class="system-state-row"><span>WSS</span><strong>${cfg.wss_configured?esc(tr('configured')):esc(tr('notConfigured'))}</strong></div><div class="system-state-row"><span>${esc(tr('signing'))}</span><strong>${cfg.signing_configured?esc(tr('configured')):esc(tr('notConfigured'))}</strong></div></article><article class="panel system-card"><h3>${esc(tr('workers'))}</h3>${taskRows||'—'}</article></div>
      <article class="panel settings-card chain-settings-card"><div class="form-heading"><span class="form-icon">⛓</span><div><strong>${esc(tr('chainConfigTitle'))}</strong><small>${esc(tr('chainConfigHint'))}</small></div></div><div class="secret-status-grid"><div><span>${esc(tr('rpcCurrent'))}</span><strong>${esc(cfgSafe.rpc_provider||tr('notConfigured'))}</strong></div><div><span>${esc(tr('wssCurrent'))}</span><strong>${esc(cfgSafe.wss_provider||tr('notConfigured'))}</strong></div><div><span>${esc(tr('seedCurrent'))}</span><strong>${esc(cfgSafe.seed_configured?tr('secretConfigured'):tr('secretMissing'))}</strong></div></div><label class="settings-field"><span>${esc(tr('chainMode'))}</span><select id="chainMode" class="select-input">${modeOptions}</select></label><div class="settings-grid chain-public-grid"><label class="settings-field"><span>${esc(tr('tokenContract'))}</span><input id="chainTokenContract" class="text-input" maxlength="42" value="${esc(cfgSafe.token_contract||'')}" placeholder="0x…"></label><label class="settings-field"><span>${esc(tr('scanStartBlock'))}</span><input id="chainScanStart" class="text-input" type="number" min="0" step="1" inputmode="numeric" value="${esc(cfgSafe.scan_start_block||0)}"></label></div><label class="settings-field"><span>${esc(tr('treasuryDerived'))}</span><input class="text-input readonly-input" readonly value="${esc(cfgSafe.treasury_address||'—')}"></label><div class="secret-fields"><label class="settings-field"><span>${esc(tr('rpcEndpoint'))} · ${esc(tr('writeOnly'))}</span><input id="chainRpcUrl" class="text-input" type="password" autocomplete="new-password" placeholder="https://…"></label><label class="settings-field"><span>${esc(tr('wssEndpoint'))} · ${esc(tr('writeOnly'))}</span><input id="chainWssUrl" class="text-input" type="password" autocomplete="new-password" placeholder="wss://…"></label><label class="settings-field"><span>${esc(tr('seedPhraseWriteOnly'))} · ${esc(tr('writeOnly'))}</span><textarea id="chainSeedPhrase" class="textarea-input compact-textarea" autocomplete="new-password" rows="3" placeholder="12 / 15 / 18 / 21 / 24 words"></textarea></label><p class="field-hint">${esc(tr('secretKeepHint'))}</p></div><p class="field-hint restart-hint">${esc(tr('restartHint'))}</p><button id="saveChainConfig" class="primary-btn" type="button">${esc(tr('saveRestart'))}</button></article>`;
    $('saveChainConfig').addEventListener('click',saveAdminChainConfig);
  }
  async function saveAdminChainConfig(){
    const token_contract=$('chainTokenContract').value.trim(), mode=$('chainMode').value, scan=Number($('chainScanStart').value);
    if(!/^0x[a-fA-F0-9]{40}$/.test(token_contract)||!Number.isFinite(scan)||scan<0){toast(tr('invalidData'),'error');return;}
    const payload={mode,token_contract,scan_start_block:Math.round(scan),rpc_url:$('chainRpcUrl').value.trim()||null,wss_url:$('chainWssUrl').value.trim()||null,seed_phrase:$('chainSeedPhrase').value.trim()||null};
    const btn=$('saveChainConfig');btn.disabled=true;
    try{await api('/api/admin/chain-config',{method:'POST',body:JSON.stringify(payload)});toast(tr('chainConfigSaved'),'success');setTimeout(()=>location.reload(),6500);}catch(e){btn.disabled=false;handleApiError(e);}
  }
  async function loadAdminLogs(){
    const rows=await api('/api/admin/audit?limit=150');
    $('adminLogsList').innerHTML=rows.length?rows.map((r)=>`<article class="list-card"><div class="list-card-header"><strong>${esc(r.event_type)}</strong><span class="date-text">${esc(fmtDate(r.created_at))}</span></div><div class="log-details">${esc(r.details||'—')}</div></article>`).join(''):`<div class="empty-state">${esc(tr('noLogs'))}</div>`;
  }

  async function boot(){
    applyTranslations();
    await loadTelegramSession();
    syncTelegramContext();
    await exchangeBotLogin();
    try{const data=verifyBootstrapIdentity(await captureAuthSession(await api('/api/bootstrap',{cache:'no-store'})));render(data);const view=qs.get('view');if(view==='admin'&&data.auth&&data.auth.is_admin)switchView('admin');else if(view&&document.getElementById(`view-${view}`))switchView(view);loadNotifications({silent:true});state.refreshTimer=setInterval(refreshBootstrap,30000);state.notificationTimer=setInterval(()=>loadNotifications({silent:true}),15000);}catch(e){
      // An expired stored token may be repaired by current signed initData.
      if(e&&e.status===401&&state.telegramSessionToken){
        await clearTelegramSession(); syncTelegramContext();
        try{const data=verifyBootstrapIdentity(await captureAuthSession(await api('/api/bootstrap',{cache:'no-store'})));render(data);loadNotifications({silent:true});state.refreshTimer=setInterval(refreshBootstrap,30000);state.notificationTimer=setInterval(()=>loadNotifications({silent:true}),15000);return;}catch(e2){e=e2;}
      }
      handleApiError(e);$('heroSubtitle').textContent=apiErrorText(e&&e.detail,e&&e.status)||tr('authFailed');
    }
  }

  document.querySelectorAll('.nav-btn').forEach((b)=>b.addEventListener('click',()=>switchView(b.dataset.view,{push:true})));
  document.querySelectorAll('[data-go]').forEach((b)=>b.addEventListener('click',()=>switchView(b.dataset.go,{push:true})));
  document.querySelectorAll('[data-history]').forEach((b)=>b.addEventListener('click',()=>{state.historyFilter=b.dataset.history;document.querySelectorAll('[data-history]').forEach((x)=>x.classList.toggle('active',x===b));if(state.data)renderHistory(state.data.deposits||[],state.data.payouts||[],state.data.chain||{});}));
  document.querySelectorAll('.admin-tab').forEach((b)=>b.addEventListener('click',()=>setAdminTab(b.dataset.adminTab)));
  document.querySelectorAll('[data-payout-filter]').forEach((b)=>b.addEventListener('click',()=>{state.payoutFilter=b.dataset.payoutFilter;document.querySelectorAll('[data-payout-filter]').forEach((x)=>x.classList.toggle('active',x===b));renderAdminPayoutRows();}));
  $('brandBtn').addEventListener('click',()=>switchView('home',{push:true}));$('profileBtn').addEventListener('click',()=>switchView('profile',{push:true}));$('notificationsBtn').addEventListener('click',()=>switchView('notifications',{push:true}));$('markAllNotificationsRead').addEventListener('click',markAllNotificationsRead);
  document.querySelectorAll('[data-notification-filter]').forEach((b)=>b.addEventListener('click',()=>{state.notificationFilter=b.dataset.notificationFilter;document.querySelectorAll('[data-notification-filter]').forEach((x)=>x.classList.toggle('active',x===b));renderNotifications({items:state.notifications,unread_count:state.notificationUnread});}));
  $('languageBtn').addEventListener('click',showLanguage);$('languageBackdrop').addEventListener('click',()=>$('languageSheet').classList.add('hidden'));$('languageClose').addEventListener('click',()=>$('languageSheet').classList.add('hidden'));
  $('userModalBackdrop').addEventListener('click',()=>$('userModal').classList.add('hidden'));$('userModalClose').addEventListener('click',()=>$('userModal').classList.add('hidden'));
  $('closeMiniApp').addEventListener('click',()=>{if(tg&&tg.close)tg.close();else location.reload();});
  $('saveWallet').addEventListener('click',saveWallet);$('createDeposit').addEventListener('click',createDeposit);$('copyReferral').addEventListener('click',()=>copyText($('referralLink').textContent));$('refreshTeam').addEventListener('click',loadTeam);$('withdrawReferral').addEventListener('click',withdrawReferral);
  $('profitCalcAmount').addEventListener('input',updateProfitCalculator);$('calculatorToDeposit').addEventListener('click',calculatorToDeposit);
  const openExternal=(url)=>{if(!url)return;if(tg&&tg.openTelegramLink&&url.startsWith('https://t.me/'))tg.openTelegramLink(url);else window.open(url,'_blank','noopener');};
  $('openSupport').addEventListener('click',()=>openExternal(state.data&&state.data.support_url));
  $('openChat').addEventListener('click',()=>openExternal(state.data&&state.data.chat_url));
  $('profileWallet').addEventListener('click',()=>switchView('wallet',{push:true}));
  $('refreshAdmin').addEventListener('click',()=>loadAdmin(state.adminTab));$('adminSearchBtn').addEventListener('click',()=>loadAdminUsers($('adminSearch').value.trim()));$('adminSearch').addEventListener('keydown',(e)=>{if(e.key==='Enter')loadAdminUsers($('adminSearch').value.trim());});$('sendBroadcast').addEventListener('click',sendBroadcast);$('grantAdminBtn').addEventListener('click',addAdminAccess);$('adminGrantInput').addEventListener('keydown',(e)=>{if(e.key==='Enter')addAdminAccess();});
  document.querySelectorAll('[data-format-tag]').forEach((b)=>b.addEventListener('click',()=>wrapBroadcastSelection(b.dataset.formatTag)));
  $('broadcastLinkFormat').addEventListener('click',formatBroadcastLink);$('broadcastImage').addEventListener('change',selectBroadcastImage);$('removeBroadcastImage').addEventListener('click',clearBroadcastImage);$('addBroadcastButton').addEventListener('click',addBroadcastButton);renderBroadcastButtons();

  window.addEventListener('pageshow',refreshTelegramAccountContext);
  window.addEventListener('focus',refreshTelegramAccountContext);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refreshTelegramAccountContext();});
  if(tg&&tg.onEvent){try{tg.onEvent('activated',refreshTelegramAccountContext);}catch(_){}}

  boot();
})();
