/* ==========================================
PRODUCT SEARCH
========================================== */

const searchForm =
document.querySelector(".products-search");

if(searchForm){

    searchForm.addEventListener("submit",function(e){

        e.preventDefault();

        const search =
        this.querySelector("input").value;

        console.log("Searching:",search);

    });

}

/* ==========================================
PRICE FILTER
========================================== */

const priceRange =
document.getElementById("priceRange");

const priceValue =
document.getElementById("priceValue");

if(priceRange && priceValue){

    priceRange.addEventListener("input", ()=>{

        priceValue.textContent =
        "₦" + Number(priceRange.value).toLocaleString();

    });

}

/* ==========================================
WISHLIST
========================================== */

const wishlistButtons =
document.querySelectorAll(".wishlist-btn");

wishlistButtons.forEach(button=>{

    button.addEventListener("click",()=>{

        button.classList.toggle("active");

    });

});

/* ==========================================
ADD TO CART
========================================== */

const cartButtons =
document.querySelectorAll(".cart-btn");

cartButtons.forEach(button=>{

    button.addEventListener("click",()=>{

        const originalText = button.textContent;

        button.textContent = "✓ Added";

        setTimeout(()=>{

            button.textContent = originalText;

        },1500);

    });

});

// ==========================================
// FOLLOW BUTTON
// ==========================================

const followButtons = document.querySelectorAll(".follow-btn");

followButtons.forEach(button => {

    button.addEventListener("click", () => {

        if (button.textContent.trim() === "Follow") {

            button.textContent = "Following";

            button.style.background = "#1a1a2e";

        } else {

            button.textContent = "Follow";

            button.style.background = "#16bf5c";

        }

    });

});

// ==========================================
// NEWSLETTER
// ==========================================

const newsletterForm = document.querySelector(".newsletter-form");

if(newsletterForm){

    newsletterForm.addEventListener("submit",(e)=>{

        e.preventDefault();

        const email =
        newsletterForm.querySelector("input").value.trim();

        if(email===""){

            alert("Please enter your email address.");

            return;

        }

        alert("🎉 Thank you for subscribing!");

        newsletterForm.reset();

    });

}