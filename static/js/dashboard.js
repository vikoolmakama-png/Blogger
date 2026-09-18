
function togglePlans() {
    const plans = document.getElementById("all-plans");
    const button = document.querySelector(".plans-toggle");

    plans.classList.toggle("show");
    button.classList.toggle("active");
}
