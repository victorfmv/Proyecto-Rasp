function showMsg(el, text, type) {
  el.textContent = text;
  el.className = 'msg ' + type;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.className = 'msg hidden'; }, 5000);
}

document.addEventListener('DOMContentLoaded', () => {
  const path = window.location.pathname.replace(/\/$/, '') || '/ui';
  document.querySelectorAll('nav a').forEach(a => {
    const href = a.getAttribute('href').replace(/\/$/, '');
    if (href === path) a.classList.add('active');
  });
});