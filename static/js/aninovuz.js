// 1. Telegram WebApp obyektini ishga tushirish
const tg = window.Telegram.WebApp;
tg.expand();

const translations = {
    uz: {
        abouttitle: "Aninovuz Loyihasi Haqida",
        abouttext: "O'zbekistondagi eng innovatsion anime platformasiga xush kelibsiz. Bizning maqsadimiz — sifatli kontentni har bir muxlisga yetkazishdir.",
        yoursection: "Siz uchun",
        missiontitle: "Bizning Missiyamiz",
        missiontext: "Aninovuz loyihasi 2025-yilda anime ixlosmandlari uchun qulay muhit yaratish maqsadida tashkil etilgan. Biz nafaqat anime ko'rish, balki o'zbek tili rivojiga hissa qo'shadigan sifatli dublyaj va subtitrlarni taqdim etishni o'z oldimizga maqsad qilganmiz. Bizning platformamiz Telegram WebApp texnologiyasi asosida qurilgan bo'lib, bu sizga ilova o'rnatmasdan turib, brauzer tezligida anime ko'rish imkonini beradi.",
        feat1title: "Tezkorlik",
        feat1desc: "Bizning serverlarimiz MySQL bazasi bilan optimallashtirilgan bo'lib, ma'lumotlar soniyalar ichida yuklanadi.",
        feat2title: "Xavfsizlik",
        feat2desc: "Foydalanuvchi ma'lumotlari Telegram xavfsizlik protokollari orqali himoyalangan.",
        feat3title: "Sifat",
        feat3desc: "Eng so'nggi animelar FHD formatda va o'zbekcha tarjimada taqdim etiladi.",
        guidetitle: "Botdan qanday foydalaniladi?",
        step1: "Telegramdagi <strong>@aninovuz_bot</strong> manziliga o'ting va /start buyrug'ini bosing.",
        step2: "Bot menyusidan 'Anime katalogi' bo'limiga o'ting.",
        step3: "Qiziqqan anime nomini qidiruv orqali toping yoki janr bo'yicha ko'rib chiqing.",
        statanimes: "Animelar",
        statusers: "Foydalanuvchilar",
        statsupport: "Texnik yordam",
        contactus: "Savollaringiz bormi?",
        contacttext: "Agar sizda hamkorlik yoki loyiha bo'yicha takliflar bo'lsa, biz bilan bog'laning.",
        shareus: "Admin bilan bog'lanish",
        none: "Hech biri",
        action: "Akshen",
        adventure: "Sarguzasht",
        comedy: "Komediya",
        drama: "Drama",
        fantasy: "Fantastika",
        horror: "Qo'rqinchli",
        mystery: "Sirli",
        romance: "Romantika",
        sci_fi: "Ilmiy fantastika",
        home: "Bosh sahifa",
        about: "Ma'lumot",
        services: "Anime list",
        contact: "Tarix",
        id: "ID",
        name: "Ism",
        status: "Status",
        lang1: "O'zbekcha",
        lang2: "Ruscha",
        lang3: "Inglizcha",
        search: "Qidiruv...",
        popular: "Eng mashhur",
        new: "Yangi animelar",
        rating: "Reyting",
        genres: "Janrlar",
        lang: "Til",
        search: "Qidiruv...",
        login: "Kirish",
        watch_bot: "Botda ko'rish"
    },
    ru: {
        abouttitle: "О проекте Aninovuz",
        abouttext: "Добро пожаловать на самую инновационную аниме-платформу в Узбекистане. Наша цель — предоставлять качественный контент каждому поклоннику.",
        missiontitle: "Наша миссия",
        missiontext: "Проект Aninovuz был создан в 2025 году с целью создания удобной среды для любителей аниме. Мы стремимся не только предоставить возможность смотреть аниме, но и внести вклад в развитие узбекского языка, предлагая качественный дубляж и субтитры. Наша платформа построена на технологии Telegram WebApp, что позволяет вам смотреть аниме с скоростью браузера без необходимости установки приложений.",
        feat1title: "Скорость",
        feat1desc: "Наши серверы оптимизированы с помощью MySQL базы данных, обеспечивая загрузку данных за считанные секунды.",
        feat2title: "Безопасность",
        feat2desc: "Данные пользователей защищены с помощью протоколов безопасности Telegram.",
        feat3title: "Качество",
        feat3desc: "Последние аниме представлены в формате FHD с узбекским дубляжом.",
        guidetitle: "Как использовать бот?",
        step1: "Перейдите по адресу <strong>@aninovuz_bot</strong> в Telegram и нажмите команду /start.",
        step2: "Перейдите в раздел 'Каталог аниме' в меню бота.",
        step3: "Найдите интересующее вас аниме с помощью поиска или просмотрите по жанрам.",
        statusers: "Пользователи",
        statanimes: "Аниме",
        statsupport: "Техническая поддержка",
        contactus: "Есть вопросы?",
        contacttext: "Если у вас есть предложения по сотрудничеству или проекту, свяжитесь с нами.",
        shareus: "Связаться с админом",
        yoursection: "Для вас",
        none: "Нет",
        action: "Боевик",
        adventure: "Приключения",
        comedy: "Комедия",
        drama: "Драма",
        fantasy: "Фэнтези",
        horror: "Ужасы",
        mystery: "Мистика",
        romance: "Романтика",
        sci_fi: "Научная фантастика",
        home: "Главная",
        about: "О нас",
        services: "Список аниме",
        contact: "История",
        id: "ID",
        name: "Имя",
        status: "Статус",
        lang1: "Узбекский",
        lang2: "Русский",
        lang3: "Английский",
        search: "Поиск...",
        popular: "Популярные",
        new: "Новые аниме",
        rating: "Рейтинг",
        genres: "Жанры",
        lang: "Язык",
        search: "Поиск...",
        login: "Вход",
        watch_bot: "Смотреть в боте"
    },
    en: {
        abouttitle: "About Aninovuz Project",
        abouttext: "Welcome to the most innovative anime platform in Uzbekistan. Our goal is to provide high-quality content to every anime fan.",
        missiontitle: "Our Mission",
        missiontext: "The Aninovuz project was established in 2025 with the aim of creating a convenient environment for anime enthusiasts. We aim not only to provide the opportunity to watch anime but also to contribute to the development of the Uzbek language by offering high-quality dubbing and subtitles. Our platform is built on Telegram WebApp technology, allowing you to watch anime at browser speed without the need to install applications.", 
        feat1title: "Speed",
        feat1desc: "Our servers are optimized with a MySQL database, ensuring data loads within seconds.",
        feat2title: "Security",
        feat2desc: "User data is protected through Telegram's security protocols.",
        feat3title: "Quality",
        feat3desc: "The latest anime are presented in FHD format with Uzbek dubbing.",
        guidetitle: "How to use the bot?",
        step1: "Go to <strong>@aninovuz_bot</strong> on Telegram and press the /start command.",
        step2: "Go to the 'Anime Catalog' section in the bot menu.",
        step3: "Find the anime you are interested in through search or browse by genre.",
        statusers: "Users",
        statanimes: "Animes",
        statsupport: "Technical Support",
        contactus: "Have questions?",
        contacttext: "If you have proposals for cooperation or projects, contact us.",
        shareus: "Contact Admin",
        yoursection: "For you",
        none: "None",
        action: "Action",
        adventure: "Adventure",
        comedy: "Comedy",
        drama: "Drama",
        fantasy: "Fantasy",
        horror: "Horror",
        mystery: "Mystery",
        romance: "Romance",
        sci_fi: "Sci-Fi",   
        home: "Home",
        about: "About",
        services: "Anime List",
        contact: "History",
        id: "ID",
        name: "Name",
        status: "Status",
        lang1: "Uzbek",
        lang2: "Russian",
        lang3: "English",
        search: "Search...",
        popular: "Popular",
        new: "New Anime",
        rating: "Rating",
        genres: "Genres",
        lang: "Language",
        search: "Search...",
        login: "Login",
        watch_bot: "Watch in Bot"
    }
};
const animeData = [
    { id: 1, title: "Naruto", image: "naruto.jpg", category: "popular" },
    { id: 2, title: "One Piece", image: "op.jpg", category: "new" },
    { id: 3, title: "Attack on Titan", image: "aot.jpg", category: "foryou" }
];

// Test foydalanuvchisi
const user = tg.initDataUnsafe?.user || {
    first_name: "G'iyosiddin",
    last_name: "Aninovuz",
    id: 6496620310,
    photo_url: "https://cdn-icons-png.flaticon.com/512/149/149071.png"
};

// --- ASOSIY FUNKSIYALAR ---

function applyLanguage(lang) {
    document.querySelectorAll('[data-lang]').forEach(element => {
        const key = element.getAttribute('data-lang');
        if (translations[lang] && translations[lang][key]) {
            element.innerText = translations[lang][key];
        }
    });

    document.querySelectorAll('[data-lang-placeholder]').forEach(element => {
        const key = element.getAttribute('data-lang-placeholder');
        if (translations[lang] && translations[lang][key]) {
            element.placeholder = translations[lang][key];
        }
    });
}

function createAnimeCard(anime, currentLang) {
    // Tarjimani olish (Watch in bot matni uchun)
    const btnText = translations[currentLang]?.watch_bot || "Botda ko'rish";

    return `
        <div class="anime-card">
            <img src="${anime.image}" alt="${anime.title}">
            <h3>${anime.title}</h3>
            <a href="https://t.me/aninovuz_bot?start=ani_${anime.id}" 
               class="watch-btn" 
               target="_blank">
                ${btnText} <i class="fa-brands fa-telegram"></i>
            </a>
        </div>
    `;
}

function renderAnimes() {
    const lang = localStorage.getItem('selectedLang') || 'uz';
    
    const newGrid = document.getElementById('newAnimeGrid');
    const popularGrid = document.getElementById('popularAnimeGrid');
    const forYouGrid = document.getElementById('for-you-animes');

    // Gridlarni tozalash (agar kerak bo'lsa)
    if(newGrid) newGrid.innerHTML = '';
    
    animeData.forEach(anime => {
        const cardHTML = createAnimeCard(anime, lang);
        
        // Kategoriyasiga qarab kerakli gridga qo'shish
        if (anime.category === "new" && newGrid) newGrid.innerHTML += cardHTML;
        if (anime.category === "popular" && popularGrid) popularGrid.innerHTML += cardHTML;
        if (anime.category === "foryou" && forYouGrid) forYouGrid.innerHTML += cardHTML;
    });
}

function changeLanguage() {
    // 1. Qaysi select o'zgarganini aniqlaymiz (PC yoki Mobile)
    const pcSelect = document.getElementById('language');
    const mobileSelect = document.getElementById('mobileLanguage');
    
    // Qaysi biri faol bo'lsa, o'shandan qiymatni olamiz
    // Agar PC'da o'zgarsa pcSelect.value, aks holda mobileSelect.value
    let lang = pcSelect ? pcSelect.value : 'uz';
    
    // Agar funksiya mobil menyudan chaqirilgan bo'lsa (event orqali)
    if (window.event && window.event.target.id === 'mobileLanguage') {
        lang = mobileSelect.value;
    }

    // 2. Ikkala select'ni ham bir xil tilga o'tkazamiz (Sinxronizatsiya)
    if (pcSelect) pcSelect.value = lang;
    if (mobileSelect) mobileSelect.value = lang;

    // 3. Xotiraga saqlash va tilni qo'llash
    localStorage.setItem('selectedLang', lang);
    applyLanguage(lang);
}

// --- DOM YUKLANGANDA ISHLAYDIGAN QISM ---

document.addEventListener('DOMContentLoaded', () => {
    // 1. Mobil menyu boshqaruvi
    const hamburger = document.getElementById('hamburger');
    const mobileMenu = document.getElementById('mobileMenu');
    if (hamburger && mobileMenu) {
        hamburger.addEventListener('click', () => {
            const isMenuOpen = mobileMenu.style.display === 'flex';
            mobileMenu.style.display = isMenuOpen ? 'none' : 'flex';
            hamburger.innerHTML = isMenuOpen ? '<i class="fa-solid fa-bars"></i>' : '<i class="fa-solid fa-xmark"></i>';
            document.body.style.overflow = isMenuOpen ? 'auto' : 'hidden';
        });
    }

    // 2. Foydalanuvchi ma'lumotlari
    if (user) {
        const profileBlock = document.getElementById('userProfileBlock');
        if (profileBlock) profileBlock.style.display = 'flex';

        const avatarImg = document.getElementById('userAvatar');
        if (document.getElementById('userName')) document.getElementById('userName').innerText = user.first_name;
        if (document.getElementById('userFullName')) document.getElementById('userFullName').innerText = `${user.first_name} ${user.last_name || ""}`;
        if (document.getElementById('userId')) document.getElementById('userId').innerText = user.id;

        if (user.photo_url && avatarImg) {
            avatarImg.src = user.photo_url;
        }
        setMockStatus(user.id);
    }

    // 3. Tilni tiklash
    const savedLang = localStorage.getItem('selectedLang') || 'uz';
    const langSelect = document.getElementById('language');
    if (langSelect) langSelect.value = savedLang;
    applyLanguage(savedLang);
});

// Tashqi klik orqali yopish
window.onclick = function(event) {
    if (!event.target.closest('.profile-trigger')) {
        const dropdown = document.getElementById('profileDropdown');
        if (dropdown?.classList.contains('active')) dropdown.classList.remove('active');
    }
};
function toggleProfile() {
    const dropdown = document.getElementById('profileDropdown');
    if (dropdown) {
        dropdown.classList.toggle('active');
    }
}

// HTML-dagi login tugmasi yoki profil triggerini topib, event qo'shamiz
document.addEventListener('DOMContentLoaded', () => {
    const profileTrigger = document.querySelector('.profile-trigger');
    if (profileTrigger) {
        profileTrigger.addEventListener('click', (e) => {
            e.stopPropagation(); // Tashqi klik hodisasi darhol ishlab ketmasligi uchun
            toggleProfile();
        });
    }
});
// Mobil va Desktop til tanlagichlarini bir-biriga bog'lash
function syncLanguage(mobileSelect) {
    const lang = mobileSelect.value;
    const desktopSelect = document.getElementById('language');
    
    // Desktop selectni ham yangilash
    if (desktopSelect) {
        desktopSelect.value = lang;
    }
    
    // Xotiraga saqlash va tarjimani qo'llash
    localStorage.setItem('selectedLang', lang);
    applyLanguage(lang);
}
const searchInput = document.getElementById('searchInput');
const searchResultsGrid = document.getElementById('newAnimeGrid'); // Qidiruv natijalari chiqadigan joy

searchInput.addEventListener('input', async (e) => {
    const query = e.target.value.trim();

    if (query.length < 2) {
        // Agar qidiruv bo'sh bo'lsa, sahifani qayta yuklash yoki asliga qaytarish mumkin
        return;
    }

    try {
        const response = await fetch(`/api/search?q=${query}`);
        const data = await response.json();
        
        // Asosiy gridni tozalab, natijalarni chiqaramiz
        searchResultsGrid.innerHTML = ''; 
        
        if (data.length === 0) {
            searchResultsGrid.innerHTML = '<p style="padding: 20px;">Hech narsa topilmadi...</p>';
            return;
        }

        data.forEach(anime => {
            searchResultsGrid.innerHTML += `
                <div class="anime-card">
                    <img src="/image/${anime.poster_id}" alt="${anime.name}">
                    <h3>${anime.name}</h3>
                    <a href="https://t.me/aninovuz_bot?start=ani_${anime.id}" class="watch-btn">
                        Botda ko'rish <i class="fa-brands fa-telegram"></i>
                    </a>
                </div>
            `;
        });
    } catch (error) {
        console.error("Qidiruvda xato:", error);
    }
});
function animateCounter(id, target) {
    let count = 0;
    let speed = target / 100; // Tezlikni sozlash
    
    let timer = setInterval(() => {
        count += Math.ceil(speed);
        if (count >= target) {
            clearInterval(timer);
            count = target;
        }
        document.getElementById(id).innerText = count + "+";
    }, 20);
}

// Sahifa yuklanganda ishga tushadi
document.addEventListener('DOMContentLoaded', () => {
    // HTML-dagi sonlarni JavaScript-ga o'qiymiz
    const aCount = parseInt(document.getElementById('animeCount').innerText);
    const uCount = parseInt(document.getElementById('userCount').innerText);
    
    animateCounter('animeCount', aCount);
    animateCounter('userCount', uCount);
});