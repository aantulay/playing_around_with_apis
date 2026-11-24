async function toggleFav(btn) {
    const country = btn.getAttribute("data-country");
    if (!country) return;

    try {
        const res = await fetch("/api/favorites/toggle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ country })
        });
        if (!res.ok) return;

        const data = await res.json();
        const isSaved = Boolean(data.saved);
        btn.classList.toggle("active", isSaved);
        btn.textContent = isSaved ? "Saved" : "Save";

        const countEl = document.getElementById("fav-count");
        if (countEl && Array.isArray(data.favorites)) {
            countEl.textContent = data.favorites.length;
        }
    }   catch (err) {
        console.error("Failed to toggle favorite:", err);
    }
}

document.addEventListener("click", (event) => {
    const btn = event.target.closest(".fav-btn");
    if (btn) {
        toggleFav(btn);
    }
});