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

// 3. Žinutės kūrimas: gavėjų paieška ir „pažymėti visus“ (tik matomus)
function normalizeText(text) {
    // be didžiųjų raidžių ir diakritikų: „Žydrūnas“ atitinka „zydrunas“
    return text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function visibleRecipientBoxes() {
    var boxes = [];
    document.querySelectorAll(".recipient").forEach(function (row) {
        if (!row.hidden) { boxes.push(row.querySelector("input[name='recipients']")); }
    });
    return boxes;
}

var recipientSearch = document.getElementById("recipient-search");
if (recipientSearch) {
    recipientSearch.addEventListener("input", function () {
        var query = normalizeText(recipientSearch.value.trim());
        var shown = 0;
        document.querySelectorAll(".recipient").forEach(function (row) {
            var match = normalizeText(row.dataset.name).indexOf(query) !== -1;
            row.hidden = !match;
            if (match) { shown++; }
        });
        document.getElementById("recipient-empty").hidden = shown !== 0;
    });
    // Enter lauke neturi išsiųsti formos
    recipientSearch.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); }
    });
}

var selectAllBtn = document.querySelector("[data-select-all]");
if (selectAllBtn) {
    selectAllBtn.addEventListener("click", function () {
        var boxes = visibleRecipientBoxes();
        var allChecked = boxes.every(function (b) { return b.checked; });
        boxes.forEach(function (b) { b.checked = !allChecked; });
    });
}

// 4. Pranešimų varpelis ir ženkleliai (periodinis atnaujinimas)
var notifBtn = document.getElementById("notif-btn");
var notifPanel = document.getElementById("notif-panel");
var notifList = document.getElementById("notif-list");
var notifBadge = document.getElementById("notif-badge");
var msgBadge = document.getElementById("msg-badge");

function setBadge(el, count) {
    if (!el) { return; }
    el.textContent = count;
    el.hidden = !count;
}

function renderNotifications(items) {
    notifList.innerHTML = "";
    if (!items.length) {
        var empty = document.createElement("li");
        empty.className = "notif-empty muted small";
        empty.textContent = "Pranešimų nėra.";
        notifList.appendChild(empty);
        return;
    }
    items.forEach(function (n) {
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.href = n.url;
        a.className = "notif-item" + (n.is_read ? "" : " unread");
        var title = document.createElement("strong");
        title.textContent = n.title;
        var preview = document.createElement("span");
        preview.className = "notif-preview";
        preview.textContent = n.preview;
        var time = document.createElement("span");
        time.className = "notif-time";
        time.textContent = n.created_at;
        a.appendChild(title);
        a.appendChild(preview);
        a.appendChild(time);
        li.appendChild(a);
        notifList.appendChild(li);
    });
}

function pollStatus() {
    fetch("/api/status", { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            setBadge(notifBadge, data.unread_notifications);
            setBadge(msgBadge, data.unread_messages);
            renderNotifications(data.notifications);
        })
        .catch(function () {});
}

if (notifBtn && notifPanel) {
    notifBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        notifPanel.hidden = !notifPanel.hidden;
        if (!notifPanel.hidden) { pollStatus(); }
    });
    document.addEventListener("click", function (e) {
        if (!notifPanel.contains(e.target)) { notifPanel.hidden = true; }
    });
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { notifPanel.hidden = true; }
    });
    document.getElementById("notif-read-all").addEventListener("click", function () {
        fetch("/notifications/read-all", { method: "POST", credentials: "same-origin" })
            .then(pollStatus)
            .catch(function () {});
    });
    pollStatus();
    setInterval(pollStatus, 8000);
}

// 5. Žinutės puslapis: perskaitymo statuso atnaujinimas ir pranešimas apie naujus atsakymus
var threadBox = document.querySelector("[data-message-id]");
if (threadBox) {
    var knownReplies = parseInt(threadBox.dataset.replyCount, 10);
    var repliesBanner = document.getElementById("new-replies");
    var pollMessage = function () {
        fetch("/api/messages/" + threadBox.dataset.messageId + "/status", { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                (data.recipients || []).forEach(function (r) {
                    var el = document.querySelector("[data-read-status='" + r.id + "']");
                    if (!el) { return; }
                    if (r.read_at) {
                        el.textContent = "Perskaityta · " + r.read_at.slice(0, 16);
                        el.className = "status status-read";
                    } else {
                        el.textContent = "Neperskaityta";
                        el.className = "status status-unread";
                    }
                });
                if (repliesBanner && data.reply_count !== undefined && data.reply_count !== knownReplies) {
                    repliesBanner.hidden = false;
                }
            })
            .catch(function () {});
    };
    setInterval(pollMessage, 5000);
}

// 6. Išsiųstų žinučių sąrašas atsinaujina pats
if (document.querySelector("[data-autorefresh]")) {
    setInterval(function () { window.location.reload(); }, 10000);
}

// Datos pasirinkimas lietuvių kalba
if (window.flatpickr) {
    flatpickr.localize(flatpickr.l10ns.lt);
    flatpickr("input[type=date]", {
        altInput: true,        // rodo gražų formatą, forma vis tiek siunčia YYYY-MM-DD
        altFormat: "Y-m-d",
        dateFormat: "Y-m-d",
        disableMobile: true    // telefonuose irgi naudoti šį kalendorių
    });
}