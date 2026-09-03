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
  const audioImage = document.querySelector('[data-localized-audio]');
  if (audioImage) {
    audioImage.src = language === 'zh'
      ? 'assets/screenshots/vremoter-audio-1.1.0.png'
      : 'assets/screenshots/vremoter-audio-1.1.0-en.png';
  }
  const mappingImage = document.querySelector('[data-localized-mapping]');
  if (mappingImage) {
    mappingImage.src = language === 'zh'
      ? 'assets/screenshots/vremoter-mapping-chromecast-1.1.0.png'
      : 'assets/screenshots/vremoter-mapping-chromecast-1.1.0-en.png';
  }
  localStorage.setItem('vremoter-language', language);
}

languageButtons.forEach((button) => {
  button.addEventListener('click', () => applyLanguage(button.dataset.setLanguage));
});

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
