// ============================================
// PASSWORD TOGGLE
// ============================================

const togglePassword = document.getElementById("togglePassword");
const passwordInput = document.getElementById("password");

if (togglePassword && passwordInput) {
    togglePassword.addEventListener("click", () => {
        const type = passwordInput.getAttribute("type") === "password" ? "text" : "password";
        passwordInput.setAttribute("type", type);
        togglePassword.textContent = type === "password" ? "👁" : "🙈";
    });
}

// ============================================
// SMOOTH PAGE ENTRANCE
// ============================================

window.addEventListener("load", () => {
    document.body.classList.add("loaded");
});

// ============================================
// LOGIN FORM HANDLER (Updated with Backend)
// ============================================

const loginForm = document.getElementById("loginForm");
const loginBtn = document.getElementById("loginBtn") || loginForm?.querySelector(".primary-btn");
const errorMessage = document.getElementById("errorMessage");
const errorText = document.getElementById("errorText");

// Function to show error
function showError(message) {
    if (errorMessage && errorText) {
        errorText.textContent = message;
        errorMessage.style.display = "block";
        errorMessage.style.animation = "none";
        // Trigger reflow for animation reset
        void errorMessage.offsetHeight;
        errorMessage.style.animation = "shake 0.5s ease";

        if (loginBtn) {
            loginBtn.classList.remove("loading", "success");
            loginBtn.classList.add("error");
        }

        // Auto-hide after 5 seconds
        setTimeout(() => {
            if (errorMessage) {
                errorMessage.style.display = "none";
            }
            if (loginBtn) {
                loginBtn.classList.remove("error");
                loginBtn.textContent = "Sign In";
                loginBtn.disabled = false;
            }
        }, 5000);
    } else {
        // Fallback if error element doesn't exist
        alert(message);
        if (loginBtn) {
            loginBtn.textContent = "Sign In";
            loginBtn.disabled = false;
            loginBtn.classList.remove("loading", "success", "error");
        }
    }
}

// Function to hide error
function hideError() {
    if (errorMessage) {
        errorMessage.style.display = "none";
    }
    if (loginBtn) {
        loginBtn.classList.remove("error");
    }
}

// Handle form submission
if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        // Hide any previous error
        hideError();

        const email = document.getElementById("email")?.value.trim();
        const password = document.getElementById("password")?.value;
        const remember = document.getElementById("remember")?.checked || false;

        // Client-side validation
        if (!email || !password) {
            showError("Please fill in all fields.");
            return;
        }

        // Email format validation
        const emailPattern = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
        if (!emailPattern.test(email)) {
            showError("Please enter a valid email address.");
            return;
        }

        // Show loading state
        if (loginBtn) {
            loginBtn.textContent = "Signing In...";
            loginBtn.disabled = true;
            loginBtn.classList.add("loading");
            loginBtn.classList.remove("success", "error");
        }

        try {
            // Send request to backend
            const response = await fetch("/login", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    email: email,
                    password: password,
                    remember: remember
                })
            });

            const result = await response.json();

            if (result.success) {
                // ✅ SUCCESS - Show success state
                if (loginBtn) {
                    loginBtn.textContent = "✓ Welcome Back!";
                    loginBtn.classList.remove("loading", "error");
                    loginBtn.classList.add("success");
                    loginBtn.style.background = "linear-gradient(135deg, #0b8f47, #0d6b35)";
                }

                // Redirect after delay
                setTimeout(() => {
                    window.location.href = result.redirect || "/dashboard";
                }, 1500);

            } else {
                // ❌ ERROR - Show error message
                showError(result.message || "Login failed. Please try again.");
                if (loginBtn) {
                    loginBtn.textContent = "Sign In";
                    loginBtn.disabled = false;
                    loginBtn.classList.remove("loading", "success");
                }
            }

        } catch (error) {
            // 🌐 NETWORK ERROR
            console.error("Login error:", error);
            showError("Network error. Please check your connection and try again.");
            if (loginBtn) {
                loginBtn.textContent = "Sign In";
                loginBtn.disabled = false;
                loginBtn.classList.remove("loading", "success");
            }
        }
    });
}

// ============================================
// CLEAR ERROR ON USER INPUT
// ============================================

const emailInput = document.getElementById("email");
const passwordInputField = document.getElementById("password");

if (emailInput) {
    emailInput.addEventListener("input", hideError);
}
if (passwordInputField) {
    passwordInputField.addEventListener("input", hideError);
}

// ============================================
// KEYBOARD SHORTCUT: Press Enter to submit
// ============================================

document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && loginForm) {
        const activeElement = document.activeElement;
        if (activeElement && (activeElement.id === "email" || activeElement.id === "password")) {
            loginForm.dispatchEvent(new Event("submit"));
        }
    }
});