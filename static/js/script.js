function togglePassword() {
    const input = document.getElementById("password");
    const eye = document.querySelector(".eye");
    if (!input) return;

    if (input.type === "password") {
        input.type = "text";
        if (eye) eye.textContent = "🙈";
    } else {
        input.type = "password";
        if (eye) eye.textContent = "👁️";
    }
}
