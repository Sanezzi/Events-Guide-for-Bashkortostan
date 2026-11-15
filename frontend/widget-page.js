const input = new URLSearchParams(location.search);
const params = new URLSearchParams({limit: "5"});
for (const name of ["city", "category", "period", "date_from", "date_to"]) {
    if (input.has(name)) params.set(name, input.get(name));
}
const status = document.getElementById("status");
fetch("/api/v1/events?" + params, {credentials: "omit"})
    .then(response => {
        if (!response.ok) throw new Error("catalog unavailable");
        return response.json();
    })
    .then(data => {
        status.textContent = data.events.length ? "" : "Подходящих событий нет. Попробуйте расширить период.";
        for (const event of data.events) {
            const item = document.createElement("li");
            const link = document.createElement("a");
            link.href = "/event?id=" + encodeURIComponent(event.id);
            link.target = "_blank";
            link.rel = "noopener";
            link.textContent = event.title;
            const date = new Intl.DateTimeFormat("ru-RU", {
                dateStyle: "short", timeStyle: "short", timeZone: "Asia/Yekaterinburg"
            }).format(new Date(event.date_start));
            item.append(link, document.createTextNode(" · " + date + " · " + event.city));
            document.getElementById("events").append(item);
        }
    }).catch(() => { status.textContent = "Не удалось загрузить афишу."; });;
