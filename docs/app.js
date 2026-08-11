const languageButtons = document.querySelectorAll('[data-set-language]');
const translatedElements = document.querySelectorAll('[data-zh][data-en]');
let language = localStorage.getItem('vremoter-language') ||
  (navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en');

function applyLanguage(nextLanguage) {
  language = nextLanguage;
  document.documentElement.lang = language === 'zh' ? 'zh-Hans' : 'en';
  translatedElements.forEach((element) => {
    element.textContent = element.dataset[language];
  });
  languageButtons.forEach((button) => {
    button.classList.toggle('active', button.dataset.setLanguage === language);
  });
  const heroSource = language === 'zh'
    ? 'assets/commerce/x6-vibe-coding-hero-v2.png'
    : 'assets/commerce/x6-vibe-coding-hero-en.png';
  document.querySelectorAll('[data-localized-hero]').forEach((image) => {
    image.src = heroSource;
  });
  const consoleImage = document.querySelector('[data-localized-console]');
  if (consoleImage) {
    consoleImage.src = language === 'zh'
      ? 'assets/commerce/vremoter-console.png'
      : 'assets/commerce/vremoter-console-en.png';
  }
  localStorage.setItem('vremoter-language', language);
  renderStores(window.commerceConfig);
}

languageButtons.forEach((button) => {
  button.addEventListener('click', () => applyLanguage(button.dataset.setLanguage));
});

const fallbackCommerce = {
  stores: [{
    id: 'xiaohongshu',
    enabled: true,
    nameZh: '小红书',
    nameEn: 'Xiaohongshu',
    url: 'https://xhslink.com/m/3E0dFZwiR9R',
    qrImageURL: 'assets/commerce/xiaohongshu-qr.png'
  }]
};

function renderStores(config = fallbackCommerce) {
  window.commerceConfig = config || fallbackCommerce;
  const stores = window.commerceConfig.stores.filter((store) => store.enabled && store.url);
  const tabs = document.querySelector('.store-tabs');
  const content = document.querySelector('.store-content');
  if (!tabs || !content) return;
  tabs.innerHTML = '';
  if (!stores.length) {
    content.innerHTML = `<p>${language === 'zh' ? '购买链接暂不可用' : 'Purchase links are temporarily unavailable'}</p>`;
    return;
  }

  const showStore = (store) => {
    [...tabs.children].forEach((button) => button.classList.toggle('active', button.dataset.store === store.id));
    content.dataset.store = store.id;
    const title = language === 'zh' ? store.nameZh : store.nameEn;
    const qrSource = store.qrImageURL || `assets/commerce/${store.id}-qr.png`;
    content.innerHTML = `
      <img src="${qrSource}" alt="${title} QR code">
      <h3>${title}</h3>
      <p>${language === 'zh' ? '用手机扫码，或在当前设备直接打开购买链接。' : 'Scan with your phone, or open the store on this device.'}</p>
      <a href="${store.url}" target="_blank" rel="noopener">${language === 'zh' ? '打开购买链接 ↗' : 'Open store ↗'}</a>`;
  };

  stores.forEach((store, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.store = store.id;
    button.textContent = language === 'zh' ? store.nameZh : store.nameEn;
    button.addEventListener('click', () => showStore(store));
    tabs.appendChild(button);
    if (index === 0) showStore(store);
  });
}

fetch('https://updates.vincentstudio.org/vremoter/commerce.json', { cache: 'no-store' })
  .then((response) => response.ok ? response.json() : Promise.reject(new Error('config')))
  .then(renderStores)
  .catch(() => renderStores(fallbackCommerce));

const donationAssets = {
  wechat: ['assets/donate/wechat.JPG', 'WeChat payment QR code'],
  alipay: ['assets/donate/alipay.JPG', 'Alipay payment QR code'],
  paypal: ['assets/donate/paypal.JPG', 'PayPal payment QR code']
};
document.querySelectorAll('[data-donation]').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('[data-donation]').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    const [source, alt] = donationAssets[button.dataset.donation];
    const image = document.querySelector('#donation-code');
    image.src = source;
    image.alt = alt;
  });
});

applyLanguage(language);
