/* ==========================================
   MARKETPLACE
========================================== */

const searchForm =
document.querySelector(".marketplace-search");

if(searchForm){

    searchForm.addEventListener("submit",function(e){

        e.preventDefault();

        const keyword =
        document.getElementById("searchInput").value.trim();

        if(keyword){

            console.log("Searching:",keyword);

            // Search functionality will be connected later.

        }

    });

}

/* ==========================================
   CATEGORY CARDS
========================================== */

const categoryCards =
document.querySelectorAll(".category-card");

categoryCards.forEach(card=>{

    card.addEventListener("click",()=>{

        const category =
        card.querySelector("h3").textContent;

        console.log(category);

        // Later we'll redirect to the appropriate
        // category page.

    });

});

/* ==========================================
   COURSE CARDS
========================================== */

const courseButtons =
document.querySelectorAll(".course-btn");

courseButtons.forEach(button=>{

    button.addEventListener("click",()=>{

        window.location.href =
        "courses/course-details.html";

    });

});

/* ==========================================
   PRODUCT CARDS
========================================== */

const productButtons =
document.querySelectorAll(".product-btn");

productButtons.forEach(button=>{

    button.addEventListener("click",()=>{

        console.log("Added to cart");

        // Later:
        // Add product to cart
        // Update cart icon
        // Save to backend

    });

});

const wishlistButtons =
document.querySelectorAll(".wishlist-btn");

wishlistButtons.forEach(button=>{

    button.addEventListener("click",()=>{

        button.classList.toggle("active");

        button.innerHTML =
        button.classList.contains("active")
        ? "❤"
        : "♡";

    });

});

/* ==========================================
   TOP VENDORS
========================================== */

const followButtons =
document.querySelectorAll(".follow-btn");

followButtons.forEach(button=>{

    button.addEventListener("click",()=>{

        if(button.textContent==="Follow"){

            button.textContent="Following";

        }

        else{

            button.textContent="Follow";

        }

    });

});

const storeButtons =
document.querySelectorAll(".store-btn");

storeButtons.forEach(button=>{

    button.addEventListener("click",()=>{

        window.location.href=
        "vendors/vendor-store.html";

    });

});

/* ==========================================
   RECOMMENDED
========================================== */

const recommendButtons =
document.querySelectorAll(".primary-small-btn");

recommendButtons.forEach(button=>{

    button.addEventListener("click",()=>{

        const text =
        button.textContent.trim();

        if(text==="View Course"){

            window.location.href=
            "courses/course-details.html";

        }

        else{

            window.location.href=
            "products/product-details.html";

        }

    });

});

/* ==========================================
   TRENDING
========================================== */

document.querySelectorAll(".outline-small-btn")

.forEach(button=>{

    button.addEventListener("click",()=>{

        window.location.href="products/product-details.html";

    });

});

/* ==========================================
   RECENTLY VIEWED
========================================== */

document.querySelectorAll(".recent-card")

.forEach(card=>{

    card.addEventListener("mouseenter",()=>{

        card.style.cursor="pointer";

    });

});

document.querySelectorAll(".primary-small-btn")

.forEach(button=>{

    button.addEventListener("click",()=>{

        window.location.href="products/product-details.html";

    });

});

/* ==========================================
   LEARNING PATHS
========================================== */

document.querySelectorAll(".path-card")

.forEach(card=>{

    card.addEventListener("mouseenter",()=>{

        card.style.cursor="pointer";

    });

});

document.querySelectorAll(".path-card .primary-small-btn")

.forEach(button=>{

    button.addEventListener("click",()=>{

        window.location.href="courses/course-details.html";

    });

});

/* ==========================================
   POPULAR COLLECTIONS
========================================== */

document.querySelectorAll(".collection-card")

.forEach(card=>{

    card.addEventListener("mouseenter",()=>{

        card.style.cursor="pointer";

    });

});

document.querySelectorAll(".collection-card .primary-small-btn")

.forEach(button=>{

    button.addEventListener("click",()=>{

        window.location.href="collections/collection-details.html";

    });

});

/* ==========================================
   EVENTS
========================================== */

document.querySelectorAll(".event-card .primary-small-btn")

.forEach(button=>{

    button.addEventListener("click",()=>{

        window.location.href="events/event-details.html";

    });

});

/* ==========================================
   COMMUNITY
========================================== */

document.querySelectorAll(".community-card .primary-small-btn")

.forEach(button=>{

    button.addEventListener("click",()=>{

        window.location.href="../community/groups.html";

    });

});

/* ==========================================
   NEWSLETTER
========================================== */

const newsletterForm =
document.querySelector(".newsletter-form");

if(newsletterForm){

    newsletterForm.addEventListener("submit",function(e){

        e.preventDefault();

        alert("Thanks for subscribing to BizHub!");

        this.reset();

    });

}