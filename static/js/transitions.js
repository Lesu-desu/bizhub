const links = document.querySelectorAll('a');

links.forEach(link => {
  link.addEventListener('click', function(e) {

    const target = this.getAttribute('href');

    if (target && !target.startsWith('#')) {
      e.preventDefault();

      document.body.style.opacity = '0';
      document.body.style.transition = '0.35s ease';

      setTimeout(() => {
        window.location.href = target;
      }, 300);
    }
  });
});