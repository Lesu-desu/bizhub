const tabs = document.querySelectorAll('.tab');
const forms = document.querySelectorAll('.auth-form');

// Tab Switching

tabs.forEach(tab => {
  tab.addEventListener('click', () => {

    tabs.forEach(btn => btn.classList.remove('active'));
    forms.forEach(form => form.classList.remove('active'));

    tab.classList.add('active');

    const target = tab.dataset.tab;

    if (target === 'login') {
      document.getElementById('loginForm').classList.add('active');
    } else {
      document.getElementById('signupForm').classList.add('active');
    }
  });
});

// Password Toggle

const toggleButtons = document.querySelectorAll('.toggle-password');

toggleButtons.forEach(button => {
  button.addEventListener('click', () => {

    const input = document.getElementById(button.dataset.target);

    if (input.type === 'password') {
      input.type = 'text';
      button.textContent = '🙈';
    } else {
      input.type = 'password';
      button.textContent = '👁';
    }
  });
});

// Vendor Field Toggle

const roleInputs = document.querySelectorAll('input[name="account_type"]');
const vendorFields = document.querySelector('.vendor-fields');
const roleCards = document.querySelectorAll('.role-card');

roleInputs.forEach(input => {
  input.addEventListener('change', () => {

    roleCards.forEach(card => {
      card.classList.remove('active-role');
    });

    input.closest('.role-card').classList.add('active-role');

    if (input.value === 'vendor') {
      vendorFields.classList.add('show');
    } else {
      vendorFields.classList.remove('show');
    }
  });
});

// Backend-Friendly Submit Prevention (temporary)

const loginForm = document.getElementById('loginForm');
const signupForm = document.getElementById('signupForm');

loginForm.addEventListener('submit', (e) => {
  e.preventDefault();

  console.log('Login form ready for backend integration');
});

signupForm.addEventListener('submit', (e) => {
  e.preventDefault();

  console.log('Signup form ready for backend integration');
});