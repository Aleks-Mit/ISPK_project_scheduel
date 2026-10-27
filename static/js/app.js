// app.js – maža JavaScript dalis

// 1. Slaptažodžio rodymas / slėpimas
document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
    button.addEventListener("click", function () {
        var input = document.getElementById(button.dataset.togglePassword);
        var show = input.type === "password";
        input.type = show ? "text" : "password";
        button.textContent = show ? "Slėpti" : "Rodyti";
    });
});

// 2. Mobilusis meniu: atidaryti / uždaryti šoninį meniu
var menuButton = document.getElementById("menu-btn");
var overlay = document.getElementById("sidebar-overlay");

if (menuButton && overlay) {
    menuButton.addEventListener("click", function () {
        document.body.classList.toggle("nav-open");
    });
    overlay.addEventListener("click", function () {
        document.body.classList.remove("nav-open");
    });
}