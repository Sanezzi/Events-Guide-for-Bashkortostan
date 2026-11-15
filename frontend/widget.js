(() => {
    const script = document.currentScript;
    if (!script) return;
    const source = new URL("/widget", script.src);
    for (const key of ["city", "category", "period", "dateFrom", "dateTo"]) {
        if (script.dataset[key]) {
            source.searchParams.set(key.replace(/[A-Z]/g, letter => "_" + letter.toLowerCase()), script.dataset[key]);
        }
    }
    const frame = document.createElement("iframe");
    frame.src = source.toString();
    frame.title = "Афиша культуры Башкортостана";
    frame.loading = "lazy";
    frame.width = "100%";
    frame.height = String(Math.max(200, Math.min(1200, Number(script.dataset.height) || 520)));
    frame.style.cssText = "display:block;border:0;width:100%";
    if (document.body?.contains(script)) {
        script.after(frame);
    } else if (document.body) {
        document.body.append(frame);
    } else {
        document.addEventListener("DOMContentLoaded", () => document.body.append(frame), {once: true});
    }
})();
