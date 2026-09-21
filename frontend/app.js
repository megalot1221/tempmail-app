const API = "";

let state = {
    user: null,
    sessionToken: localStorage.getItem("guest_session_token"),
    mailbox: null,
    mailboxes: [],
    domains: [],
    country: null,
    timer: null,
    inboxTimer: null,
    autoRefresh: true,
    currentEmails: [],
    openedEmail: null
};

/* =========================================================
   HELPERS
========================================================= */

const $ = (id) => document.getElementById(id);

function setText(id, value) {
    const el = $(id);
    if (el) el.textContent = value ?? "";
}

function escapeHTML(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function authHeaders() {
    const token = localStorage.getItem("access_token");

    return token
        ? { Authorization: `Bearer ${token}` }
        : {};
}

async function request(url, options = {}) {
    const response = await fetch(API + url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        }
    });

    const text = await response.text();

    let data = {};

    try {
        data = text ? JSON.parse(text) : {};
    } catch {
        data = { detail: text };
    }

    if (!response.ok) {
        throw new Error(
            data.detail ||
            data.message ||
            `Request failed (${response.status})`
        );
    }

    return data;
}

function toast(message) {
    const el = $("toast");

    if (!el) {
        console.log(message);
        return;
    }

    el.textContent = message;
    el.classList.add("show");

    setTimeout(() => {
        el.classList.remove("show");
    }, 3000);
}

function formatDate(value) {
    if (!value) return "—";

    try {
        return new Date(value).toLocaleString();
    } catch {
        return String(value);
    }
}

function formatEmailDate(value) {
    if (!value) return "—";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    return date.toLocaleString();
}

function getEmailSender(email) {
    return (
        email?.from_address ||
        email?.from ||
        email?.sender ||
        "Unknown sender"
    );
}

function getEmailSubject(email) {
    return (
        email?.subject ||
        email?.title ||
        "(No subject)"
    );
}

function getEmailDate(email) {
    return (
        email?.received_at ||
        email?.created_at ||
        email?.timestamp ||
        email?.date ||
        email?.sent_at ||
        ""
    );
}

function getEmailText(email) {
    return (
        email?.body_plain ||
        email?.body_text ||
        email?.plain_text ||
        email?.text ||
        email?.body ||
        email?.content ||
        email?.message ||
        email?.preview ||
        ""
    );
}

function getEmailHTML(email) {
    return (
        email?.body_html ||
        email?.html ||
        email?.html_body ||
        email?.html_content ||
        ""
    );
}

function normalizeEmailDetail(data) {
    /*
     * Upstream normally returns the message object directly.
     * Some versions wrap it in "email" or "data".
     */
    if (data?.email && typeof data.email === "object") {
        return data.email;
    }

    if (
        data?.data &&
        typeof data.data === "object" &&
        !Array.isArray(data.data)
    ) {
        return data.data;
    }

    return data || {};
}

function sanitizeEmailHTML(html) {
    if (!html) return "";

    try {
        const parser = new DOMParser();
        const doc = parser.parseFromString(
            String(html),
            "text/html"
        );

        /*
         * Never execute JavaScript contained in an email.
         */
        doc
            .querySelectorAll(
                "script, iframe, object, embed, form, base, meta"
            )
            .forEach((node) => node.remove());

        /*
         * Remove inline event handlers and dangerous URLs.
         */
        doc.querySelectorAll("*").forEach((node) => {
            [...node.attributes].forEach((attribute) => {
                const name = attribute.name.toLowerCase();
                const value = attribute.value.trim();

                if (name.startsWith("on")) {
                    node.removeAttribute(attribute.name);
                    return;
                }

                if (
                    (name === "href" || name === "src" || name === "action") &&
                    /^javascript:/i.test(value)
                ) {
                    node.removeAttribute(attribute.name);
                }
            });
        });

        /*
         * Verification links must remain clickable.
         */
        doc.querySelectorAll("a[href]").forEach((link) => {
            link.setAttribute("target", "_blank");
            link.setAttribute("rel", "noopener noreferrer");
        });

        return doc.body.innerHTML;
    } catch {
        return escapeHTML(String(html));
    }
}

function ensureEmailModal() {
    let modal = $("emailModal");

    if (modal) {
        return modal;
    }

    modal = document.createElement("div");
    modal.id = "emailModal";
    modal.className = "email-modal hidden";

    modal.innerHTML = `
        <div class="email-modal-backdrop"></div>

        <div
            class="email-modal-card glass"
            role="dialog"
            aria-modal="true"
            aria-labelledby="emailModalSubject"
        >
            <div class="email-modal-header">
                <div class="email-modal-title-wrap">
                    <span class="badge">MESSAGE</span>
                    <h2 id="emailModalSubject">
                        No subject
                    </h2>
                </div>

                <button
                    type="button"
                    class="email-modal-close"
                    id="emailModalClose"
                    aria-label="Close message"
                >
                    ×
                </button>
            </div>

            <div class="email-meta">
                <div>
                    <span>From</span>
                    <strong id="emailModalFrom">—</strong>
                </div>

                <div>
                    <span>Date</span>
                    <strong id="emailModalDate">—</strong>
                </div>
            </div>

            <div class="email-message-tabs">
                <button
                    type="button"
                    class="email-message-tab active"
                    data-email-tab="html"
                >
                    HTML
                </button>

                <button
                    type="button"
                    class="email-message-tab"
                    data-email-tab="text"
                >
                    Plain text
                </button>
            </div>

            <div
                id="emailHTMLPanel"
                class="email-message-html"
            ></div>

            <pre
                id="emailTextPanel"
                class="email-message-text hidden"
            ></pre>

            <div
                id="emailMessageLoading"
                class="email-message-loading hidden"
            >
                Loading full message...
            </div>

            <div
                id="emailMessageError"
                class="email-message-error hidden"
            ></div>
        </div>
    `;

    document.body.appendChild(modal);

    modal
        .querySelector(".email-modal-backdrop")
        ?.addEventListener(
            "click",
            closeEmailModal
        );

    modal
        .querySelector("#emailModalClose")
        ?.addEventListener(
            "click",
            closeEmailModal
        );

    modal
        .querySelectorAll("[data-email-tab]")
        .forEach((button) => {
            button.addEventListener("click", () => {
                switchEmailTab(
                    button.dataset.emailTab
                );
            });
        });

    return modal;
}

function switchEmailTab(tab) {
    const htmlPanel = $("emailHTMLPanel");
    const textPanel = $("emailTextPanel");

    document
        .querySelectorAll("[data-email-tab]")
        .forEach((button) => {
            button.classList.toggle(
                "active",
                button.dataset.emailTab === tab
            );
        });

    htmlPanel?.classList.toggle(
        "hidden",
        tab !== "html"
    );

    textPanel?.classList.toggle(
        "hidden",
        tab !== "text"
    );
}

function showEmailModalLoading(show) {
    $("emailMessageLoading")
        ?.classList.toggle("hidden", !show);

    if (show) {
        $("emailMessageError")
            ?.classList.add("hidden");
    }
}

function showEmailModalError(message) {
    const error = $("emailMessageError");

    if (!error) return;

    error.textContent = message || "Unable to load message.";
    error.classList.remove("hidden");
}

function closeEmailModal() {
    const modal = $("emailModal");

    if (!modal) return;

    modal.classList.add("hidden");
    document.body.classList.remove("email-modal-open");

    const iframe = modal.querySelector(
        "#emailMessageFrame"
    );

    if (iframe) {
        iframe.remove();
    }

    const htmlPanel = $("emailHTMLPanel");

    if (htmlPanel) {
        htmlPanel.innerHTML = "";
    }

    const textPanel = $("emailTextPanel");

    if (textPanel) {
        textPanel.textContent = "";
    }

    state.openedEmail = null;
}

async function openEmailMessage(index) {
    const summary = state.currentEmails?.[index];

    if (!summary) {
        toast("Message not found.");
        return;
    }

    const modal = ensureEmailModal();

    state.openedEmail = summary;

    setText(
        "emailModalSubject",
        getEmailSubject(summary)
    );

    setText(
        "emailModalFrom",
        getEmailSender(summary)
    );

    setText(
        "emailModalDate",
        formatEmailDate(getEmailDate(summary))
    );

    const htmlPanel = $("emailHTMLPanel");
    const textPanel = $("emailTextPanel");

    if (htmlPanel) htmlPanel.innerHTML = "";
    if (textPanel) textPanel.textContent = "";

    switchEmailTab("html");

    modal.classList.remove("hidden");
    document.body.classList.add("email-modal-open");

    showEmailModalLoading(true);

    const messageId =
        summary.id ??
        summary.email_id ??
        summary.message_id ??
        summary.uuid;

    if (
        messageId === undefined ||
        messageId === null ||
        String(messageId).trim() === ""
    ) {
        /*
         * If the list response itself contains the full body,
         * display it without making another request.
         */
        displayFullEmail(summary);
        showEmailModalLoading(false);
        return;
    }

    try {
        let data;

        if (state.user) {
            data = await request(
                `/api/user/mailbox/${state.mailbox.id}/emails/${encodeURIComponent(
                    String(messageId)
                )}`,
                {
                    headers: authHeaders()
                }
            );
        } else {
            if (!state.sessionToken) {
                throw new Error("Guest session has expired.");
            }

            data = await request(
                `/api/guest/mailbox/${state.mailbox.id}/emails/${encodeURIComponent(
                    String(messageId)
                )}?session_token=${encodeURIComponent(
                    state.sessionToken
                )}`
            );
        }

        console.log("Full email response:", data);

        const detail = normalizeEmailDetail(data);

        console.log("Normalized email detail:", detail);

        displayFullEmail(detail);

        showEmailModalLoading(false);

    } catch (error) {
        console.error(
            "Full email loading failed:",
            error
        );

        /*
         * Fall back to whatever the list endpoint supplied.
         */
        displayFullEmail(summary);

        const hasBody =
            getEmailText(summary) ||
            getEmailHTML(summary);

        if (!hasBody) {
            showEmailModalError(
                error.message ||
                "Unable to load the full message."
            );
        }
    } finally {
        showEmailModalLoading(false);
    }
}

function displayFullEmail(email) {
    const html =
        sanitizeEmailHTML(
            getEmailHTML(email)
        );

    const text =
        getEmailText(email);

    const htmlPanel =
        $("emailHTMLPanel");

    const textPanel =
        $("emailTextPanel");

    if (htmlPanel) {
        if (html) {
            htmlPanel.innerHTML = html;
        } else if (text) {
            htmlPanel.innerHTML = `
                <div class="email-no-html">
                    This message does not contain HTML.
                    Open <strong>Plain text</strong> to view it.
                </div>
            `;
        } else {
            htmlPanel.innerHTML = `
                <div class="email-no-html">
                    No message body was returned.
                </div>
            `;
        }
    }

    if (textPanel) {
        textPanel.textContent =
            text ||
            "No plain-text version available.";
    }

    setText(
        "emailModalSubject",
        getEmailSubject(email)
    );

    setText(
        "emailModalFrom",
        getEmailSender(email)
    );

    setText(
        "emailModalDate",
        formatEmailDate(getEmailDate(email))
    );
}

/* =========================================================
   VIEW ROUTING
========================================================= */

function showView(name) {
    const views = [
        "mailbox",
        "account",
        "settings",
        "myEmails",
        "admin",
        "adminUsers",
        "adminDomains",
        "adminMailboxes"
    ];

    views.forEach((view) => {
        const el = $(`${view}View`);

        if (!el) return;

        el.classList.toggle("hidden", view !== name);
    });

    document
        .querySelectorAll(".nav-item[data-view]")
        .forEach((item) => {
            item.classList.toggle(
                "active",
                item.dataset.view === name
            );
        });

    const titles = {
        mailbox: "Your private inbox",
        account: "Account settings",
        settings: "Settings",
        myEmails: "My emails",
        admin: "Admin dashboard",
        adminUsers: "Users",
        adminDomains: "Domains",
        adminMailboxes: "Mailboxes"
    };

    setText("pageTitle", titles[name] || "TempMail");

    closeMobileMenu();
}

/* =========================================================
   AUTH UI
========================================================= */

function updateAuthUI(user) {
    const loginBtn = $("loginBtn");
    const logoutBtn = $("logoutBtn");
    const adminNav = $("adminNav");
    const mobileAdminNav = $("mobileAdminNav");

    if (user) {
        loginBtn?.classList.add("hidden");
        logoutBtn?.classList.remove("hidden");

        if (user.role === "admin") {
            adminNav?.classList.remove("hidden");
            mobileAdminNav?.classList.remove("hidden");
        } else {
            adminNav?.classList.add("hidden");
            mobileAdminNav?.classList.add("hidden");
        }

        updateAccountUI(user);
    } else {
        loginBtn?.classList.remove("hidden");
        logoutBtn?.classList.add("hidden");
        adminNav?.classList.add("hidden");
        mobileAdminNav?.classList.add("hidden");
    }
}

function updateAccountUI(user) {
    if (!user) return;

    setText("accountUsername", user.username || "—");
    setText("accountEmail", user.email || "—");
    setText("accountCountry", user.country || "Unknown");
    setText("accountRole", user.role || "user");

    setText("settingsUsername", user.username || "—");
    setText("settingsEmail", user.email || "—");

    $("registerForm")?.classList.add("hidden");
    $("accountInfo")?.classList.remove("hidden");

    setText("accountTitle", "Account settings");
    setText(
        "accountDescription",
        "Manage your TempMail account."
    );
}

/* =========================================================
   CURRENT USER
========================================================= */

async function loadCurrentUser() {
    const token = localStorage.getItem("access_token");

    if (!token) {
        state.user = null;
        updateAuthUI(null);
        return null;
    }

    try {
        const data = await request(
            "/api/auth/me",
            {
                headers: authHeaders()
            }
        );

        state.user = data.user || data;

        updateAuthUI(state.user);

        if (state.user.role === "admin") {
            showView("admin");
            await loadAdminDashboard();
        } else {
            showView("mailbox");
            await loadUserMailboxes();
        }

        return state.user;
    } catch (error) {
        console.error(error);

        localStorage.removeItem("access_token");
        state.user = null;

        updateAuthUI(null);

        return null;
    }
}

/* =========================================================
   DOMAINS
========================================================= */

async function loadDomains() {
    try {
        const data = await request("/api/domains");

        const domains = Array.isArray(data.domains)
            ? data.domains
            : [];

        state.domains = domains;

        const select = $("domainSelect");

        if (!select) return;

        select.innerHTML = "";

        if (!domains.length) {
            select.innerHTML =
                `<option value="">No domains available</option>`;
            return;
        }

        domains.forEach((domain) => {
            const value =
                typeof domain === "string"
                    ? domain
                    : domain.domain || domain.name || "";

            if (!value) return;

            const option = document.createElement("option");

            option.value = value;
            option.textContent = "@" + value;

            select.appendChild(option);
        });

    } catch (error) {
        console.error("Domain loading failed:", error);

        const select = $("domainSelect");

        if (select) {
            select.innerHTML =
                `<option value="">Unable to load domains</option>`;
        }
    }
}

/* =========================================================
   GUEST SESSION
========================================================= */

async function createGuestSession() {
    try {
        const data = await request(
            "/api/guest/session",
            {
                method: "POST",
                body: JSON.stringify({})
            }
        );

        state.sessionToken =
            data.session_token ||
            data.token ||
            null;

        if (state.sessionToken) {
            localStorage.setItem(
                "guest_session_token",
                state.sessionToken
            );
        }

        state.country =
            data.country ||
            data.country_name ||
            null;

        return data;
    } catch (error) {
        console.error(
            "Guest session failed:",
            error
        );

        throw error;
    }
}

/* =========================================================
   NEW EMAIL MODAL
========================================================= */

function ensureNewEmailModal() {
    let modal = $("newEmailModal");

    if (modal) return modal;

    modal = document.createElement("div");
    modal.id = "newEmailModal";
    modal.className = "email-modal hidden";

    modal.innerHTML = `
        <div class="email-modal-backdrop"></div>

        <div class="email-modal-card glass">
            <div class="email-modal-header">
                <div>
                    <span class="badge">NEW EMAIL</span>
                    <h2>Create mailbox</h2>
                </div>

                <button
                    type="button"
                    class="email-modal-close"
                    id="newEmailModalClose"
                >×</button>
            </div>

            <div class="new-email-options">

                <button
                    type="button"
                    class="new-email-option"
                    id="randomEmailOption"
                >
                    <span class="new-email-option-icon">⚡</span>
                    <span>
                        <strong>Random email</strong>
                        <small>
                            
                        </small>
                    </span>
                </button>

                <div class="new-email-designated">
                    <div class="new-email-option-title">
                        <span class="new-email-option-icon">✎</span>

                        <span>
                            <strong>Designated email</strong>
                            <small>
                                
                            </small>
                        </span>
                    </div>

                    <div class="designated-email-row">
                        <input
                            id="designatedEmailUsername"
                            type="text"
                            maxlength="64"
                            placeholder="your-name"
                            autocomplete="off"
                            spellcheck="false"
                        />

                        <span></span>

                        <select id="designatedEmailDomain"></select>
                    </div>

                    <button
                        type="button"
                        class="button primary"
                        id="createDesignatedEmailBtn"
                    >
                        Create designated email
                    </button>
                </div>

            </div>

            <div
                id="newEmailMessage"
                class="form-message"
            ></div>
        </div>
    `;

    document.body.appendChild(modal);

    const close = () => {
        modal.classList.add("hidden");

        const message = $("newEmailMessage");
        if (message) message.textContent = "";
    };

    modal
        .querySelector(".email-modal-backdrop")
        ?.addEventListener("click", close);

    modal
        .querySelector("#newEmailModalClose")
        ?.addEventListener("click", close);

    modal
        .querySelector("#randomEmailOption")
        ?.addEventListener("click", async () => {
            const message = $("newEmailMessage");

            if (message) {
                message.textContent = "Creating random email...";
            }

            try {
                close();
                await createMailbox({
                    forceNew: true
                });

                toast("New permanent email created.");
            } catch (error) {
                console.error(error);

                if (message) {
                    message.textContent =
                        error.message ||
                        "Unable to create email.";
                }
            }
        });

    modal
        .querySelector("#createDesignatedEmailBtn")
        ?.addEventListener("click", async () => {
            const input = $("designatedEmailUsername");
            const domainSelect =
                $("designatedEmailDomain");
            const message = $("newEmailMessage");

            const username =
                input?.value.trim().toLowerCase();

            const domain =
                domainSelect?.value || "";

            if (!username) {
                if (message) {
                    message.textContent =
                        "Enter a mailbox name.";
                }

                input?.focus();
                return;
            }

            if (!domain) {
                if (message) {
                    message.textContent =
                        "Select a domain.";
                }

                return;
            }

            if (message) {
                message.textContent =
                    "Creating designated email...";
            }

            try {
                const data = await request(
                    "/api/user/mailbox",
                    {
                        method: "POST",
                        headers: authHeaders(),
                        body: JSON.stringify({
                            domain,
                            username
                        })
                    }
                );

                const created =
                    data.mailbox || data;

                if (!created?.id) {
                    throw new Error(
                        "Mailbox was not returned by the server."
                    );
                }

                state.mailbox = created;

                await loadUserMailboxes({
                    selectFirst: false
                });

                const createdId =
                    Number(created.id);

                const matched =
                    state.mailboxes.find(
                        (item) =>
                            Number(item.id) ===
                            createdId
                    );

                if (matched) {
                    state.mailbox = matched;
                }

                close();

                showView("mailbox");
                renderMailbox();
                await loadInbox();

                toast(
                    "Designated email created successfully."
                );

            } catch (error) {
                console.error(
                    "Designated mailbox creation failed:",
                    error
                );

                if (message) {
                    message.textContent =
                        error.message ||
                        "Unable to create designated email.";
                }
            }
        });

    return modal;
}

function openNewEmailModal() {
    if (!state.user) {
        openModal("loginModal");
        return;
    }

    const modal = ensureNewEmailModal();

    const select =
        $("designatedEmailDomain");

    if (select) {
        select.innerHTML = "";

        const domains =
            Array.isArray(state.domains)
                ? state.domains
                : [];

        domains.forEach((domain) => {
            const value =
                typeof domain === "string"
                    ? domain
                    : domain.domain ||
                      domain.name ||
                      "";

            if (!value) return;

            const option =
                document.createElement("option");

            option.value = value;
            option.textContent = "@" + value;

            select.appendChild(option);
        });

        if (!domains.length) {
            select.innerHTML =
                `<option value="">No verified domains</option>`;
        }
    }

    const input =
        $("designatedEmailUsername");

    if (input) {
        input.value = "";
    }

    const message =
        $("newEmailMessage");

    if (message) {
        message.textContent = "";
    }

    modal.classList.remove("hidden");
}

/* =========================================================
   MAILBOX
========================================================= */

async function createMailbox(options = {}) {
    const { forceNew = false } = options;

    const setMailboxLoading = (message = "Creating mailbox...") => {
        setText("emailAddress", message);
        setText("domainName", "—");
        setText("countryName", "—");
        const copyBtn = $("copyBtn");
        if (copyBtn) copyBtn.disabled = true;
    };

    try {
        setMailboxLoading();

        if (state.user) {
            if (!forceNew) {
                await loadUserMailboxes();

                if (state.mailbox) {
                    renderMailbox();
                    await loadInbox();
                    return state.mailbox;
                }
            }

            const domain = $("domainSelect")?.value || "";
            const data = await request("/api/user/mailbox", {
                method: "POST",
                headers: authHeaders(),
                body: JSON.stringify({
                    domain: domain || null
                })
            });

            state.mailbox = data.mailbox || data;

            await loadUserMailboxes();

            const createdId = Number(
                state.mailbox?.id ??
                data.mailbox?.id ??
                data.id
            );

            const matched = state.mailboxes.find(
                (item) => Number(item.id) === createdId
            );

            if (matched) {
                state.mailbox = matched;
            }
        } else {
            // A guest session can expire. If mailbox creation fails once,
            // create a fresh guest session and retry exactly once.
            if (!state.sessionToken) {
                await createGuestSession();
            }

            const domain = $("domainSelect")?.value || "";
            let data;

            try {
                data = await request(
                    `/api/guest/mailbox?session_token=${encodeURIComponent(state.sessionToken)}`,
                    {
                        method: "POST",
                        body: JSON.stringify({
                            domain: domain || null
                        })
                    }
                );
            } catch (firstError) {
                console.warn("Guest mailbox creation retry:", firstError);

                await createGuestSession();

                data = await request(
                    `/api/guest/mailbox?session_token=${encodeURIComponent(state.sessionToken)}`,
                    {
                        method: "POST",
                        body: JSON.stringify({
                            domain: domain || null
                        })
                    }
                );
            }

            state.mailbox = data.mailbox || data;
        }

        if (!state.mailbox) {
            throw new Error("Mailbox was not returned by the server.");
        }

        renderMailbox();
        await loadInbox();

        return state.mailbox;
    } catch (error) {
        console.error("Mailbox creation failed:", error);

        setText(
            "emailAddress",
            "Unable to create mailbox"
        );
        setText("domainName", "—");
        setText("countryName", "—");

        const copyBtn = $("copyBtn");
        if (copyBtn) copyBtn.disabled = true;

        toast(error.message || "Unable to create mailbox");
        return null;
    }
}

async function loadUserMailboxes(options = {}) {
    const { selectFirst = true } = options;

    try {
        const data = await request("/api/user/mailboxes", {
            headers: authHeaders()
        });

        state.mailboxes = Array.isArray(data.mailboxes)
            ? data.mailboxes
            : [];

        if (state.mailboxes.length) {
            if (!state.mailbox || selectFirst) {
                state.mailbox = state.mailboxes[0];
            }

            const currentId = Number(state.mailbox?.id);
            const current = state.mailboxes.find(
                (item) => Number(item.id) === currentId
            );

            if (current) {
                state.mailbox = current;
            }

            renderMailbox();
            await loadInbox();
        } else {
            state.mailbox = null;
        }

        return state.mailboxes;
    } catch (error) {
        console.error("User mailboxes failed:", error);
        state.mailboxes = [];
        state.mailbox = null;
        toast(error.message || "Unable to load mailboxes");
        return [];
    }
}


function renderMyEmails() {
    const list = $("myEmailsList");
    if (!list) return;

    if (!state.user) {
        list.innerHTML = `
            <div class="empty-state compact-empty">
                <div class="empty-icon">🔒</div>
                <h3>Login required</h3>
                <p>Login to view your permanent mailboxes.</p>
                <button type="button" class="button primary my-emails-login-btn">
                    Login
                </button>
            </div>
        `;

        list.querySelector(".my-emails-login-btn")
            ?.addEventListener("click", () => openModal("loginModal"));
        return;
    }

    if (!state.mailboxes.length) {
        list.innerHTML = `
            <div class="empty-state compact-empty">
                <div class="empty-icon">✉</div>
                <h3>No mailboxes yet</h3>
                <p>Create a permanent mailbox to get started.</p>
                <button type="button" class="button primary my-emails-new-btn">
                    Create mailbox
                </button>
            </div>
        `;

        list.querySelector(".my-emails-new-btn")
            ?.addEventListener("click", async () => {
                await createMailbox({ forceNew: true });
                await renderMyEmails();
            });
        return;
    }

    list.innerHTML = state.mailboxes.map((mailbox) => {
        const domain =
            mailbox.domain ||
            mailbox.domain_name ||
            (
                mailbox.email?.includes("@")
                    ? mailbox.email.split("@")[1]
                    : ""
            );

        const mailboxId = Number(mailbox.id);

        return `
            <div class="my-email-item">
                <div class="my-email-info">
                    <strong>${escapeHTML(mailbox.email || "—")}</strong>
                    <span>${escapeHTML(domain)}</span>
                </div>

                <button
                    type="button"
                    class="button secondary open-mailbox-btn"
                    data-mailbox-id="${Number.isFinite(mailboxId) ? mailboxId : ""}"
                >
                    Open inbox →
                </button>
            </div>
        `;
    }).join("");

    list.querySelectorAll(".open-mailbox-btn").forEach((button) => {
        button.addEventListener("click", async () => {
            const mailboxId = Number(button.dataset.mailboxId);

            const mailbox = state.mailboxes.find(
                (item) => Number(item.id) === mailboxId
            );

            if (!mailbox) {
                toast("Mailbox not found");
                return;
            }

            state.mailbox = mailbox;
            showView("mailbox");
            renderMailbox();
            await loadInbox();
        });
    });
}

function renderMailbox() {
    const mailbox = state.mailbox;

    if (!mailbox) return;

    setText(
        "emailAddress",
        mailbox.email || "—"
    );

    setText(
        "domainName",
        mailbox.domain ||
        mailbox.domain_name ||
        (
            mailbox.email &&
            mailbox.email.includes("@")
                ? mailbox.email.split("@")[1]
                : "—"
        )
    );

    setText(
        "countryName",
        mailbox.country || "Unknown"
    );

    const copyBtn = $("copyBtn");

    if (copyBtn) {
        copyBtn.disabled = !mailbox.email;
    }

    startCountdown(mailbox.expires_at);
}

/* =========================================================
   COUNTDOWN
========================================================= */

function startCountdown(expiresAt) {
    clearInterval(state.timer);

    const countdown = $("countdown");

    if (!countdown) return;

    if (!expiresAt) {
        countdown.textContent = "Permanent";
        return;
    }

    const update = () => {
        const remaining =
            new Date(expiresAt).getTime() -
            Date.now();

        if (remaining <= 0) {
            countdown.textContent = "Expired";
            clearInterval(state.timer);
            return;
        }

        const totalSeconds =
            Math.floor(remaining / 1000);

        const minutes =
            Math.floor(totalSeconds / 60);

        const seconds =
            totalSeconds % 60;

        countdown.textContent =
            `${String(minutes).padStart(2, "0")}:` +
            `${String(seconds).padStart(2, "0")}`;
    };

    update();

    state.timer =
        setInterval(update, 1000);
}

/* =========================================================
   INBOX
========================================================= */

async function loadInbox() {
    if (!state.mailbox) return;

    try {
        let data;

        if (state.user) {
            data = await request(
                `/api/user/mailbox/${state.mailbox.id}/emails`,
                {
                    headers: authHeaders()
                }
            );
        } else {
            if (!state.sessionToken) return;

            data = await request(
                `/api/guest/mailbox/${state.mailbox.id}/emails?session_token=${encodeURIComponent(
                    state.sessionToken
                )}`
            );
        }

        const emails =
            Array.isArray(data.emails)
                ? data.emails
                : [];

        renderInbox(emails);

    } catch (error) {
        console.error(
            "Inbox failed:",
            error
        );
    }
}

function renderInbox(emails) {
    const inbox = $("inbox");

    if (!inbox) return;

    state.currentEmails =
        Array.isArray(emails)
            ? emails
            : [];

    setText(
        "messageCount",
        state.currentEmails.length
    );

    if (!state.currentEmails.length) {
        inbox.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">✉</div>

                <h3>Your inbox is empty</h3>

                <p>
                    Messages sent to your temporary
                    address will appear here automatically.
                </p>
            </div>
        `;

        setText(
            "inboxStatus",
            "Waiting for messages"
        );

        return;
    }

    setText(
        "inboxStatus",
        `${state.currentEmails.length} message${
            state.currentEmails.length === 1
                ? ""
                : "s"
        } received`
    );

    inbox.innerHTML = state.currentEmails
        .map((email, index) => {
            const sender =
                getEmailSender(email);

            const subject =
                getEmailSubject(email);

            const preview =
                String(
                    email.preview ||
                    email.body_preview ||
                    email.text ||
                    email.body_text ||
                    ""
                )
                .replace(/\s+/g, " ")
                .trim()
                .slice(0, 220);

            const date =
                getEmailDate(email);

            return `
                <div
                    class="email-row email-row-clickable"
                    data-email-index="${index}"
                    role="button"
                    tabindex="0"
                    aria-label="Open email: ${escapeHTML(subject)}"
                >
                    <div class="email-row-top">
                        <span class="email-from">
                            ${escapeHTML(sender)}
                        </span>

                        <span class="email-time">
                            ${escapeHTML(
                                formatEmailDate(date)
                            )}
                        </span>
                    </div>

                    <div class="email-subject">
                        ${escapeHTML(subject)}
                    </div>

                    <div class="email-preview">
                        ${escapeHTML(
                            preview ||
                            "Click to open full message."
                        )}
                    </div>

                    <div class="email-open-hint">
                        Open message →
                    </div>
                </div>
            `;
        })
        .join("");

    inbox
        .querySelectorAll(".email-row-clickable")
        .forEach((row) => {
            const open = () => {
                openEmailMessage(
                    Number(row.dataset.emailIndex)
                );
            };

            row.addEventListener("click", open);

            row.addEventListener(
                "keydown",
                (event) => {
                    if (
                        event.key === "Enter" ||
                        event.key === " "
                    ) {
                        event.preventDefault();
                        open();
                    }
                }
            );
        });
}

/* =========================================================
   ADMIN DASHBOARD
========================================================= */

let adminAnalyticsChart = null;

async function loadAdminDashboard() {
    if (
        !state.user ||
        state.user.role !== "admin"
    ) {
        return;
    }

    try {
        const [
            dashboard,
            activity,
            analytics
        ] = await Promise.all([
            request(
                "/api/admin/dashboard",
                {
                    headers: authHeaders()
                }
            ),

            request(
                "/api/admin/activity",
                {
                    headers: authHeaders()
                }
            ),

            request(
                "/api/admin/analytics",
                {
                    headers: authHeaders()
                }
            )
        ]);

        const users =
            dashboard.users || {};

        const mailboxes =
            dashboard.mailboxes || {};

        const domains =
            dashboard.domains || {};

        setText(
            "adminRegisteredUsers",
            Number(
                users.registered || 0
            ).toLocaleString()
        );

        setText(
            "adminActiveMailboxes",
            Number(
                mailboxes.active || 0
            ).toLocaleString()
        );

        setText(
            "adminTotalMailboxes",
            Number(
                mailboxes.total || 0
            ).toLocaleString()
        );

        setText(
            "adminVerifiedDomains",
            Number(
                domains.verified || 0
            ).toLocaleString()
        );

        setText(
            "adminPendingDomains",
            Number(
                domains.pending || 0
            ).toLocaleString()
        );

        const rows =
            Array.isArray(analytics.analytics)
                ? analytics.analytics
                : [];

        const generated =
            rows.reduce(
                (total, row) =>
                    total +
                    Number(
                        row.emails_generated || 0
                    ),
                0
            );

        const received =
            rows.reduce(
                (total, row) =>
                    total +
                    Number(
                        row.emails_received || 0
                    ),
                0
            );

        setText(
            "adminEmailsGenerated",
            generated.toLocaleString()
        );

        setText(
            "adminEmailsReceived",
            received.toLocaleString()
        );

        const pendingStatus =
            $("adminPendingStatus");

        if (pendingStatus) {
            if (Number(domains.pending || 0) > 0) {
                pendingStatus.textContent = "CHECK";
                pendingStatus.className =
                    "alert-status warning";
            } else {
                pendingStatus.textContent = "OK";
                pendingStatus.className =
                    "alert-status success";
            }
        }

        renderAdminAnalytics(rows);

        renderAdminRecentActivity(
            activity.activities || []
        );

        if (state.user.username) {
            setText(
                "adminProfileName",
                state.user.username
            );

            setText(
                "adminAvatar",
                state.user.username
                    .charAt(0)
                    .toUpperCase()
            );
        }

    } catch (error) {
        console.error(
            "Admin dashboard failed:",
            error
        );

        toast(
            error.message ||
            "Unable to load admin dashboard"
        );
    }
}

function renderAdminAnalytics(rows) {
    const canvas =
        $("adminAnalyticsChart");

    if (
        !canvas ||
        typeof Chart === "undefined"
    ) {
        return;
    }

    if (adminAnalyticsChart) {
        adminAnalyticsChart.destroy();
    }

    const labels = rows.map((row) => {
        const date = new Date(row.date);

        return date.toLocaleDateString(
            [],
            {
                month: "short",
                day: "numeric"
            }
        );
    });

    const generated =
        rows.map((row) =>
            Number(
                row.emails_generated || 0
            )
        );

    const received =
        rows.map((row) =>
            Number(
                row.emails_received || 0
            )
        );

    const ctx =
        canvas.getContext("2d");

    adminAnalyticsChart =
        new Chart(ctx, {
            type: "line",

            data: {
                labels,

                datasets: [
                    {
                        label: "Generated",
                        data: generated,
                        borderColor: "#ff642e",
                        backgroundColor:
                            "rgba(255,91,35,.18)",
                        borderWidth: 2,
                        fill: true,
                        tension: .42,
                        pointRadius: 0
                    },

                    {
                        label: "Received",
                        data: received,
                        borderColor: "#ed5ca4",
                        backgroundColor:
                            "rgba(238,91,163,.14)",
                        borderWidth: 2,
                        fill: true,
                        tension: .42,
                        pointRadius: 0
                    }
                ]
            },

            options: {
                responsive: true,
                maintainAspectRatio: false,

                interaction: {
                    mode: "index",
                    intersect: false
                },

                plugins: {
                    legend: {
                        display: false
                    }
                },

                scales: {
                    x: {
                        grid: {
                            display: false
                        }
                    },

                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
}

function renderAdminRecentActivity(activities) {
    const tbody =
        $("adminRecentActivity");

    if (!tbody) return;

    const recent =
        Array.isArray(activities)
            ? activities.slice(0, 6)
            : [];

    if (!recent.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="table-loading">
                    No recent activity.
                </td>
            </tr>
        `;

        return;
    }

    tbody.innerHTML =
        recent
            .map((activity) => {
                const event =
                    escapeHTML(
                        activity.event ||
                        "Activity"
                    );

                const country =
                    escapeHTML(
                        activity.country ||
                        "Unknown"
                    );

                const date =
                    activity.created_at
                        ? new Date(
                            activity.created_at
                        ).toLocaleString()
                        : "—";

                return `
                    <tr>
                        <td>
                            <span class="activity-event">
                                ${event}
                            </span>
                        </td>

                        <td>
                            <span class="activity-country">
                                ${country}
                            </span>
                        </td>

                        <td>
                            ${escapeHTML(date)}
                        </td>

                        <td>
                            <span class="activity-status">
                                Recorded
                            </span>
                        </td>
                    </tr>
                `;
            })
            .join("");
}

/* =========================================================
   ADMIN PAGES
========================================================= */

async function loadAdminUsers() {
    try {
        const data =
            await request(
                "/api/admin/users",
                {
                    headers: authHeaders()
                }
            );

        const list =
            $("adminUsersList");

        if (!list) return;

        const users =
            Array.isArray(data.users)
                ? data.users
                : [];

        if (!users.length) {
            list.innerHTML =
                "No users found.";
            return;
        }

        list.innerHTML =
            users.map((user) => `
                <div class="admin-list-item">
                    <strong>
                        ${escapeHTML(
                            user.username || "—"
                        )}
                    </strong>

                    <span>
                        ${escapeHTML(
                            user.email || "—"
                        )}
                    </span>

                    <small>
                        ${escapeHTML(
                            user.country || "Unknown"
                        )}
                    </small>
                </div>
            `).join("");

    } catch (error) {
        console.error(error);
        toast(error.message);
    }
}

async function loadAdminMailboxes() {
    try {
        const data =
            await request(
                "/api/admin/mailboxes",
                {
                    headers: authHeaders()
                }
            );

        const list =
            $("adminMailboxesList");

        if (!list) return;

        const mailboxes =
            Array.isArray(data.mailboxes)
                ? data.mailboxes
                : [];

        if (!mailboxes.length) {
            list.innerHTML =
                "No mailboxes found.";
            return;
        }

        list.innerHTML =
            mailboxes.map((mailbox) => `
                <div class="admin-list-item">
                    <strong>
                        ${escapeHTML(
                            mailbox.email || "—"
                        )}
                    </strong>

                    <span>
                        ${escapeHTML(
                            mailbox.mailbox_type || "—"
                        )}
                    </span>

                    <small>
                        ${escapeHTML(
                            mailbox.country || "Unknown"
                        )}
                    </small>
                </div>
            `).join("");

    } catch (error) {
        console.error(error);
        toast(error.message);
    }
}

async function loadAdminDomains() {
    try {
        const data =
            await request(
                "/api/admin/domains",
                {
                    headers: authHeaders()
                }
            );

        const list =
            $("adminDomainsList");

        if (!list) return;

        const domains =
            Array.isArray(data.domains)
                ? data.domains
                : [];

        if (!domains.length) {
            list.innerHTML =
                "No domains found.";
            return;
        }

        list.innerHTML =
            domains.map((domain) => `
                <div class="admin-list-item">
                    <strong>
                        ${escapeHTML(
                            domain.domain || "—"
                        )}
                    </strong>

                    <span>
                        ${escapeHTML(
                            domain.status || "pending"
                        )}
                    </span>

                    <small>
                        ${domain.verified_at
                            ? escapeHTML(
                                formatDate(
                                    domain.verified_at
                                )
                            )
                            : "Not verified"}
                    </small>
                </div>
            `).join("");

    } catch (error) {
        console.error(error);
        toast(error.message);
    }
}

/* =========================================================
   AUTH
========================================================= */

async function register() {
    const username =
        $("registerUsername")?.value.trim();

    const email =
        $("registerEmail")?.value.trim();

    const password =
        $("registerPassword")?.value;

    const message =
        $("registerMessage");

    if (!username || !email || !password) {
        if (message) {
            message.textContent =
                "Please fill in all fields.";
        }

        return;
    }

    try {
        const data =
            await request(
                "/api/auth/register",
                {
                    method: "POST",
                    body: JSON.stringify({
                        username,
                        email,
                        password
                    })
                }
            );

        /*
         * Registration must NOT automatically
         * log the user in.
         */
        localStorage.removeItem(
            "access_token"
        );

        state.user = null;

        updateAuthUI(null);

        if (message) {
            message.textContent =
                "Account created. Please log in.";
        }

        toast("Account created successfully.");

        $("loginEmail").value = email;

        setTimeout(() => {
            openModal("loginModal");
        }, 500);

    } catch (error) {
        console.error(error);

        if (message) {
            message.textContent =
                error.message ||
                "Registration failed.";
        }
    }
}

async function login() {
    const email =
        $("loginEmail")?.value.trim();

    const password =
        $("loginPassword")?.value;

    const message =
        $("loginMessage");

    if (!email || !password) {
        if (message) {
            message.textContent =
                "Enter your email and password.";
        }

        return;
    }

    if (message) {
        message.textContent = "Logging in...";
    }

    try {
        const data = await request(
            "/api/auth/login",
            {
                method: "POST",
                body: JSON.stringify({
                    email,
                    password
                })
            }
        );

        const token =
            data.access_token ||
            data.token;

        if (!token) {
            throw new Error(
                "No access token returned."
            );
        }

        localStorage.setItem("access_token", token);
        state.sessionToken = null;
        localStorage.removeItem("guest_session_token");

        let user = data.user;

        if (!user) {
            const me =
                await request(
                    "/api/auth/me",
                    {
                        headers: authHeaders()
                    }
                );

            user = me.user || me;
        }

        state.user = user;

        updateAuthUI(user);

        $("loginModal")
            ?.classList.add("hidden");

        if (user.role === "admin") {
            showView("admin");
            await loadAdminDashboard();
        } else {
            showView("mailbox");
            await loadUserMailboxes();

            if (!state.mailbox) {
                await createMailbox();
            }
        }

        toast("Login successful.");

    } catch (error) {
        console.error(
            "Login error:",
            error
        );

        if (message) {
            message.textContent =
                error.message ||
                "Login failed.";
        }
    }
}

async function getUserFromToken() {
    const data =
        await request(
            "/api/auth/me",
            {
                headers: authHeaders()
            }
        );

    return data.user || data;
}

/* =========================================================
   MODALS
========================================================= */

function openModal(id) {
    $(id)?.classList.remove("hidden");
}

function closeModal(id) {
    $(id)?.classList.add("hidden");
}

/* =========================================================
   MOBILE MENU
========================================================= */

function openMobileMenu() {
    const menu = $("mobileMenu");

    if (!menu) {
        console.error("mobileMenu not found");
        return;
    }

    menu.classList.remove("hidden");

    document.body.classList.add(
        "mobile-menu-open"
    );
}

function closeMobileMenu() {
    const menu = $("mobileMenu");

    if (!menu) return;

    menu.classList.add("hidden");

    document.body.classList.remove(
        "mobile-menu-open"
    );
}

/* =========================================================
   SIDEBAR
========================================================= */


function setupMobileNewEmailButton() {
    if (document.getElementById("mobileNewMailboxBtn")) return;

    const btn = document.createElement("button");
    btn.id = "mobileNewMailboxBtn";
    btn.type = "button";
    btn.textContent = "+ New email";
    btn.addEventListener("click", () => {
        if (typeof openNewEmailModal === "function") {
            openNewEmailModal();
        } else {
            const desktopBtn = document.getElementById("newMailboxBtn");
            if (desktopBtn) desktopBtn.click();
        }
    });

    document.body.appendChild(btn);
}

function setupNewEmailButton() {
    const button = $("newMailboxBtn");

    if (!button) return;

    button.addEventListener(
        "click",
        openNewEmailModal
    );
}

function setupAdminSidebar() {
    const sidebar =
        $("mainSidebar");

    const collapseBtn =
        $("sidebarCollapseBtn");

    const adminToggle =
        $("adminSidebarToggle");

    if (!sidebar) return;

    const saved =
        localStorage.getItem(
            "adminSidebarCollapsed"
        ) === "true";

    if (saved) {
        sidebar.classList.add(
            "sidebar-collapsed"
        );
    }

    collapseBtn?.addEventListener(
        "click",
        () => {
            sidebar.classList.toggle(
                "sidebar-collapsed"
            );

            localStorage.setItem(
                "adminSidebarCollapsed",
                sidebar.classList.contains(
                    "sidebar-collapsed"
                )
            );
        }
    );

    adminToggle?.addEventListener(
        "click",
        () => {
            sidebar.classList.toggle(
                "sidebar-collapsed"
            );
        }
    );
}

/* =========================================================
   SETTINGS
========================================================= */

function setupSettings() {
    $("autoRefreshToggle")
        ?.addEventListener(
            "change",
            (event) => {
                state.autoRefresh =
                    event.target.checked;

                if (state.autoRefresh) {
                    startInboxRefresh();
                } else {
                    clearInterval(
                        state.inboxTimer
                    );
                }
            }
        );

    $("changeNameBtn")
        ?.addEventListener(
            "click",
            () => {
                toast(
                    "Name change endpoint is not configured yet."
                );
            }
        );

    $("changeEmailBtn")
        ?.addEventListener(
            "click",
            () => {
                toast(
                    "Email change endpoint is not configured yet."
                );
            }
        );

    $("changePasswordBtn")
        ?.addEventListener(
            "click",
            () => {
                toast(
                    "Password change endpoint is not configured yet."
                );
            }
        );
}

/* =========================================================
   EVENTS
========================================================= */

function setupEvents() {
    document
        .querySelectorAll(".nav-item[data-view]")
        .forEach((item) => {
            item.addEventListener("click", async (event) => {
                event.preventDefault();

                const view = item.dataset.view;
                if (!view) return;

                showView(view);

                if (view === "myEmails") {
                    if (!state.user) {
                        renderMyEmails();
                    } else {
                        await loadUserMailboxes({ selectFirst: false });
                        renderMyEmails();
                    }
                }

                if (view === "admin") {
                    await loadAdminDashboard();
                }

                if (view === "adminUsers") {
                    await loadAdminUsers();
                }

                if (view === "adminDomains") {
                    await loadAdminDomains();
                }

                if (view === "adminMailboxes") {
                    await loadAdminMailboxes();
                }
            });
        });

    $("loginBtn")?.addEventListener("click", () => {
        openModal("loginModal");
    });

    $("registerBtn")?.addEventListener("click", register);

    $("submitLogin")?.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        await login();
    });

    $("logoutBtn")?.addEventListener("click", logout);

    $("copyBtn")?.addEventListener("click", async () => {
        if (!state.mailbox?.email) return;

        try {
            await navigator.clipboard.writeText(state.mailbox.email);
            toast("Email copied.");
        } catch {
            toast("Unable to copy email.");
        }
    });

    $("newMailboxBtn")?.addEventListener("click", async () => {
        showView("mailbox");
        await createMailbox({ forceNew: Boolean(state.user) });
    });

    $("mobileNewMailboxBtn")?.addEventListener("click", async () => {
        showView("mailbox");
        await createMailbox({ forceNew: Boolean(state.user) });
    });

    $("refreshBtn")?.addEventListener("click", loadInbox);

    $("adminRefreshBtn")?.addEventListener(
        "click",
        loadAdminDashboard
    );

    $("mobileMenuBtn")?.addEventListener(
        "click",
        openMobileMenu
    );

    $("apiDocsBtn")?.addEventListener("click", () => {
        window.open("/docs", "_blank", "noopener,noreferrer");
        closeMobileMenu();
    });

    document
        .querySelectorAll(".quick-action[data-admin-action]")
        .forEach((button) => {
            button.addEventListener("click", async () => {
                const action = button.dataset.adminAction;
                if (!action) return;

                const view = `admin${action.charAt(0).toUpperCase()}${action.slice(1)}`;
                showView(view);

                if (view === "adminUsers") await loadAdminUsers();
                if (view === "adminDomains") await loadAdminDomains();
                if (view === "adminMailboxes") await loadAdminMailboxes();
            });
        });

    document
        .querySelectorAll("[data-admin-view]")
        .forEach((button) => {
            button.addEventListener("click", () => {
                if (button.dataset.adminView === "activity") {
                    toast("Recent activity is shown on the dashboard.");
                }
            });
        });

    document
        .querySelectorAll(".modal-close")
        .forEach((button) => {
            button.addEventListener("click", () => {
                button.closest(".modal")?.classList.add("hidden");
            });
        });

    document
        .querySelectorAll(".modal-backdrop")
        .forEach((backdrop) => {
            backdrop.addEventListener("click", () => {
                backdrop.closest(".modal")?.classList.add("hidden");
            });
        });

    $("domainSelect")?.addEventListener("change", async () => {
        if (!state.mailbox) return;

        // A domain change applies when generating the next mailbox.
        toast("Domain selected for the next mailbox.");
    });
}

/* =========================================================
   AUTO REFRESH
========================================================= */

function startInboxRefresh() {
    clearInterval(
        state.inboxTimer
    );

    if (!state.autoRefresh) {
        return;
    }

    state.inboxTimer =
        setInterval(
            async () => {
                if (
                    state.mailbox &&
                    document.visibilityState !==
                        "hidden"
                ) {
                    await loadInbox();
                }
            },
            10000
        );
}

/* =========================================================
   LOGOUT
========================================================= */

async function logout() {
    localStorage.removeItem(
        "access_token"
    );

    state.user = null;
    state.mailbox = null;
    state.mailboxes = [];

    updateAuthUI(null);

    showView("mailbox");

    try {
        state.sessionToken = null;
        localStorage.removeItem("guest_session_token");
        await createGuestSession();
        await createMailbox();
    } catch (error) {
        console.error(error);
    }

    toast("Logged out.");
}

/* =========================================================
   INIT
========================================================= */

async function init() {
    setupEvents();
    setupMobileSidebar();
    setupAdminSidebar();
    setupNewEmailButton();
    setupMobileNewEmailButton();
    setupSettings();

    await loadDomains();

    const user = await loadCurrentUser();

    if (!user) {
        showView("mailbox");

        try {
            await createMailbox();
        } catch (error) {
            console.error("Guest initialization failed:", error);
        }
    } else if (user.role === "user") {
        renderMailbox();
    }

    startInboxRefresh();
}
/* =========================================================
   MOBILE SIDEBAR DIRECT CLICK HANDLER
========================================================= */

function setupMobileSidebar() {
    const menuButton = $("mobileMenuBtn");
    const menu = $("mobileMenu");

    if (!menuButton || !menu) {
        return;
    }

    menuButton.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        openMobileMenu();
    });

    menu.querySelector(".mobile-menu-backdrop")
        ?.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            closeMobileMenu();
        });

    menu.querySelectorAll(".mobile-nav-item[data-view]")
        .forEach((item) => {
            item.addEventListener("click", async (event) => {
                event.preventDefault();
                event.stopPropagation();

                const view = item.dataset.view;
                if (!view) return;

                closeMobileMenu();
                showView(view);

                if (view === "myEmails") {
                    if (state.user) {
                        await loadUserMailboxes({ selectFirst: false });
                    }
                    renderMyEmails();
                }

                if (view === "admin") {
                    await loadAdminDashboard();
                }

                if (view === "adminUsers") {
                    await loadAdminUsers();
                }

                if (view === "adminDomains") {
                    await loadAdminDomains();
                }

                if (view === "adminMailboxes") {
                    await loadAdminMailboxes();
                }
            });
        });
}

document.addEventListener(
    "keydown",
    (event) => {
        if (event.key === "Escape") {
            closeEmailModal();
        }
    }
);

document.addEventListener(
    "DOMContentLoaded",
    init
);
/* =========================================================
   INLINE NEW EMAIL
   Replaces the Email Domain selector.
   ========================================================= */

function getRandomVerifiedDomain() {
    const domains = Array.isArray(state.domains) ? state.domains : [];

    const available = domains
        .map((item) => {
            if (typeof item === "string") return item;

            return (
                item?.domain ||
                item?.name ||
                ""
            );
        })
        .map((domain) => String(domain).trim().toLowerCase())
        .filter(Boolean);

    if (!available.length) {
        return "";
    }

    return available[Math.floor(Math.random() * available.length)];
}


async function createGuestRandomMailbox() {
    const button = document.getElementById("inlineNewMailboxBtn");

    try {
        if (button) {
            button.disabled = true;
            button.textContent = "Creating email...";
        }

        if (!state.sessionToken) {
            await createGuestSession();
        }

        await loadDomains();

        const randomDomain = getRandomVerifiedDomain();

        if (!randomDomain) {
            throw new Error("No verified email domains are available.");
        }

        const data = await request(
            `/api/guest/mailbox?session_token=${encodeURIComponent(state.sessionToken)}`,
            {
                method: "POST",
                body: JSON.stringify({
                    domain: randomDomain
                })
            }
        );

        state.mailbox = data.mailbox || data;

        if (!state.mailbox) {
            throw new Error("Mailbox was not returned by the server.");
        }

        renderMailbox();
        await loadInbox();

    } catch (error) {
        console.error("Guest random mailbox error:", error);
        alert(error.message || "Unable to create a new email.");
    } finally {
        if (button) {
            button.disabled = false;
            button.innerHTML = "＋ New email";
        }
    }
}


function setupInlineNewEmailButton() {
    const select = document.getElementById("domainSelect");

    if (!select) {
        console.warn("domainSelect was not found.");
        return;
    }

    /* Don't create it twice */
    if (document.getElementById("inlineNewMailboxBtn")) {
        return;
    }

    /*
     * Hide the old domain selector.
     */
    select.style.display = "none";

    /*
     * Hide the old "Email domain" label.
     */
    const parent = select.parentElement;

    if (parent) {
        const label = parent.querySelector("label");

        if (label) {
            label.style.display = "none";
        }
    }

    /*
     * Create the replacement button.
     */
    const button = document.createElement("button");

    button.id = "inlineNewMailboxBtn";
    button.type = "button";
    button.innerHTML = "＋ New email";

    /*
     * Put it exactly where the domain selector was.
     */
    select.parentElement.insertBefore(button, select);

    button.addEventListener("click", async () => {

        /*
         * Registered user:
         * use the existing New Email modal.
         */
        if (state.user) {
            if (typeof openNewEmailModal === "function") {
                openNewEmailModal();
            } else {
                const desktopButton =
                    document.getElementById("newMailboxBtn");

                if (desktopButton) {
                    desktopButton.click();
                }
            }

            return;
        }

        /*
         * Guest:
         * immediately generate a random email
         * on a random verified domain.
         */
        await createGuestRandomMailbox();
    });
}


/*
 * Initialize after the page has loaded.
 */
document.addEventListener("DOMContentLoaded", () => {
    setupInlineNewEmailButton();
});
