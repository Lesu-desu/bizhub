console.log("AUTH JS CONNECTED");

// =========================================
// FORGOT PASSWORD FLOW
// =========================================

const forgotPasswordForm = document.getElementById("forgotPasswordForm");

if (forgotPasswordForm) {

  forgotPasswordForm.addEventListener("submit", (e) => {

    e.preventDefault();

    const button =
      forgotPasswordForm.querySelector(".primary-btn");

    const forgotState =
      document.getElementById("forgotState");

    const successState =
      document.getElementById("successState");

    button.textContent = "Sending Link...";
    button.disabled = true;

    // Simulated request
    setTimeout(() => {

      forgotState.classList.add("hidden");

      successState.classList.remove("hidden");

    }, 1500);

  });

}

/* =========================================
   PASSWORD TOGGLE
========================================= */

const toggleButtons = document.querySelectorAll(".toggle-password");

toggleButtons.forEach(button => {

  button.addEventListener("click", () => {

    const input = button.previousElementSibling;

    if (input.type === "password") {
      input.type = "text";
      button.textContent = "🙈";
    } else {
      input.type = "password";
      button.textContent = "👁";
    }

  });

});

/* =========================================
   RESET PASSWORD FLOW
========================================= */

const resetPasswordForm = document.getElementById("resetPasswordForm");

if (resetPasswordForm) {

  resetPasswordForm.addEventListener("submit", (e) => {

    e.preventDefault();

    const newPassword =
      document.getElementById("newPassword").value;

    const confirmPassword =
      document.getElementById("confirmPassword").value;

    if (newPassword !== confirmPassword) {
      alert("Passwords do not match.");
      return;
    }

    document
      .getElementById("resetFormState")
      .classList.add("hidden");

    document
      .getElementById("resetSuccessState")
      .classList.remove("hidden");

  });

}

/* =========================================
   VERIFY EMAIL FLOW
========================================= */

const resendEmailBtn =
  document.getElementById("resendEmailBtn");

if (resendEmailBtn) {

  resendEmailBtn.addEventListener("click", () => {

    resendEmailBtn.classList.add("loading");

    resendEmailBtn.textContent =
      "Verification Email Sent";

    setTimeout(() => {

      resendEmailBtn.classList.remove("loading");

      resendEmailBtn.textContent =
        "Resend Verification Email";

    }, 3000);

  });

}

/* =========================================
   RESEND RESET EMAIL
========================================= */

const resendResetBtn =
  document.getElementById("resendResetBtn");

if (resendResetBtn) {

  resendResetBtn.addEventListener("click", () => {

    resendResetBtn.classList.add("loading");

    resendResetBtn.textContent =
      "Sending...";

    setTimeout(() => {

      resendResetBtn.classList.remove("loading");

      resendResetBtn.textContent =
        "Sent ✓";

      setTimeout(() => {

        resendResetBtn.textContent =
          "Resend";

      }, 2000);

    }, 1500);

  });

}

/* =========================================
   SIGNUP FLOW
========================================= */

const signupForm = document.getElementById("signupForm");

if (signupForm) {

  signupForm.addEventListener("submit", (e) => {

    e.preventDefault();

    const button = signupForm.querySelector(".primary-btn");

    button.disabled = true;
    button.textContent = "Creating Account...";

    // Simulate account creation
    setTimeout(() => {

      window.location.href = "../onboarding/choose-role.html";

    }, 1200);

  });

}

/* ==========================================
   VENDOR STEP 1
========================================== */

const vendorStep1Form =
document.getElementById("vendorStep1Form");

if (vendorStep1Form) {

    vendorStep1Form.addEventListener("submit", function (e) {

        e.preventDefault();

        // Later this is where we'll save the data
        // to the backend before moving on.

        window.location.href = "vendor-step2.html";

    });

}

/* ==========================================
   VENDOR STEP 2
========================================== */

const vendorStep2Form =
document.getElementById("vendorStep2Form");

if(vendorStep2Form){

    vendorStep2Form.addEventListener("submit",function(e){

        e.preventDefault();

        window.location.href =
        "vendor-step3.html";

    });

}

/* ==========================================
   VENDOR STEP 3
========================================== */

const vendorStep3Form =
document.getElementById("vendorStep3Form");

if(vendorStep3Form){

vendorStep3Form.addEventListener("submit",function(e){

e.preventDefault();

window.location.href="vendor-step4.html";

});

}


/* ==========================================
   VENDOR STEP 4
========================================== */

const vendorStep4Form =
document.getElementById("vendorStep4Form");

if(vendorStep4Form){

vendorStep4Form.addEventListener("submit",function(e){

e.preventDefault();

window.location.href =
"vendor-step5.html";

});

}



/* ==========================================
   VENDOR STEP 5
========================================== */

const vendorStep5Form =
document.getElementById("vendorStep5Form");

if(vendorStep5Form){

vendorStep5Form.addEventListener("submit",function(e){

e.preventDefault();

window.location.href =
"../../auth/verify-email.html";

});

}

/* ==========================================
   CUSTOMER STEP 1
========================================== */

const customerStep1Form =
document.getElementById("customerStep1Form");

if(customerStep1Form){

customerStep1Form.addEventListener("submit",function(e){

e.preventDefault();

window.location.href =
"customer-step2.html";

});

}

/* ==========================================
   CUSTOMER STEP 2
========================================== */

const customerStep2Form =
document.getElementById("customerStep2Form");

if(customerStep2Form){

customerStep2Form.addEventListener("submit",function(e){

e.preventDefault();

window.location.href =
"customer-step3.html";

});

}


/* ==========================================
   CUSTOMER STEP 3
========================================== */

const customerStep3Form =
document.getElementById("customerStep3Form");

if(customerStep3Form){

customerStep3Form.addEventListener("submit",function(e){

e.preventDefault();

window.location.href =
"customer-step4.html";

});

}

/* ==========================================
   CUSTOMER STEP 4
========================================== */

const customerStep4Form =
document.getElementById("customerStep4Form");

if(customerStep4Form){

customerStep4Form.addEventListener("submit",function(e){

e.preventDefault();

window.location.href =
"customer-step5.html";

});

}

/* ==========================================
   CUSTOMER STEP 5
========================================== */

const customerStep5Form =
document.getElementById("customerStep5Form");

if(customerStep5Form){

customerStep5Form.addEventListener("submit",function(e){

e.preventDefault();

window.location.href =
"../../auth/verify-email.html";

});

}

/* ==========================================
   EMAIL VERIFIED
========================================== */

const continueDashboardBtn =
document.getElementById("continueDashboardBtn");

if(continueDashboardBtn){

continueDashboardBtn.addEventListener("click",function(){

// Temporary dashboard
window.location.href =
"../dashboard/customer/index.html";

});

}

/* ==========================================
   VERIFY EMAIL COMPLETE
========================================== */

const emailVerifiedBtn =
document.getElementById("emailVerifiedBtn");

if(emailVerifiedBtn){

emailVerifiedBtn.addEventListener("click",function(){

window.location.href =
"email-verified.html";

});

}