(function () {
    function applyTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        var input = document.getElementById("theme-toggle-input");
        if (input) {
            input.checked = theme === "light";
        }
    }

    function currentTheme() {
        return document.documentElement.getAttribute("data-theme") || "dark";
    }

    function toggleTheme() {
        var next = currentTheme() === "dark" ? "light" : "dark";
        localStorage.setItem("sipf-theme", next);
        applyTheme(next);
    }

    function bindToggle() {
        var input = document.getElementById("theme-toggle-input");
        if (!input) {
            return;
        }

        applyTheme(currentTheme());
        input.addEventListener("change", toggleTheme);
    }

    function bindMenuToggle() {
        var menuToggle = document.getElementById("menu-toggle");
        var nav = document.getElementById("nav");
        if (!menuToggle || !nav) {
            return;
        }

        menuToggle.addEventListener("click", function() {
            nav.classList.toggle("open");
            var expanded = nav.classList.contains("open");
            menuToggle.setAttribute("aria-expanded", expanded ? "true" : "false");
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function() {
            bindToggle();
            bindMenuToggle();
        });
    } else {
        bindToggle();
        bindMenuToggle();
    }
})();
