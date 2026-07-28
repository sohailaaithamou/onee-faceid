const TOKEN_KEY = "onee_faceid_access_token";
const ACCOUNT_KEY = "onee_faceid_account";

const form = document.querySelector("#loginForm");
const button = document.querySelector("#loginButton");
const errorBox = document.querySelector("#loginError");

if (localStorage.getItem(TOKEN_KEY)) {
  window.location.replace("/dashboard");
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.classList.add("hidden");
  button.disabled = true;
  button.textContent = "Connexion…";

  const body = new URLSearchParams();
  body.set("username", document.querySelector("#username").value.trim());
  body.set("password", document.querySelector("#password").value);

  try {
    const response = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    const payload = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(payload.detail || `Erreur HTTP ${response.status}`);
    }

    localStorage.setItem(TOKEN_KEY, payload.access_token);
    localStorage.setItem(ACCOUNT_KEY, JSON.stringify(payload.account));
    window.location.replace("/dashboard");
  } catch (error) {
    showError(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Se connecter";
  }
});
