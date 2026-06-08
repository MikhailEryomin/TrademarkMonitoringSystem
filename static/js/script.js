const API_BASE_URL = "http://localhost:8000/api";
    let pollInterval = null;
    let currentScannedTM = null;

    // --- ФУНКЦИИ ВКЛАДКИ СКАНИРОВАНИЯ ---

    async function fetchTMInfo() {
        const tmNumbers = document.getElementById('tmInputScan').value.trim();
        const manualName = document.getElementById('manualNameInput').value.trim();
        if (!tmNumbers) return alert("Введите номер(а) ТЗ");

        const btn = document.getElementById('btnFindTM');
        btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Поиск...`;
        btn.disabled = true;

        try {
            let url = `${API_BASE_URL}/trademark/${tmNumbers}`;
            if (manualName) {
                url += `?manual_name=${encodeURIComponent(manualName)}`;
            }

            const res = await fetch(url);
            if (!res.ok) throw new Error("ТЗ не найден или ошибка сервера");
            const data = await res.json();

            document.getElementById('tmLogo').src = data.logo_url;
            document.getElementById('tmName').innerText = `${data.name} (${data.name_lat})`;
            document.getElementById('tmOwner').innerText = data.owner_name;

            // Вывод классов МКТУ с описанием
            let classesHtml = '';
            data.mktu.forEach((cls, index) => {
                classesHtml += `
                <div class="accordion-item">
                    <h2 class="accordion-header" id="heading${index}">
                        <button class="accordion-button collapsed py-2 px-3" type="button" data-bs-toggle="collapse" data-bs-target="#collapse${index}" aria-expanded="false" aria-controls="collapse${index}">
                            <span class="badge bg-primary me-2">${cls.number}</span>
                            <span class="small text-dark">Посмотреть рубрики</span>
                        </button>
                    </h2>
                    <div id="collapse${index}" class="accordion-collapse collapse" aria-labelledby="heading${index}" data-bs-parent="#mktuAccordion">
                        <div class="accordion-body small text-muted bg-light">
                            ${cls.description}
                        </div>
                    </div>
                </div>`;
            });
            document.getElementById('tmClasses').innerHTML = classesHtml;

            document.getElementById('tmInfoCard').classList.remove('d-none');
            document.getElementById('progressCard').classList.add('d-none');
            document.getElementById('currentResultsCard').classList.add('d-none');
            document.getElementById('btnStartScan').disabled = false;

        } catch (error) {
            alert(error.message);
            document.getElementById('tmInfoCard').classList.add('d-none');
        } finally {
            btn.innerHTML = `<i class="bi bi-search"></i> Найти ТЗ`;
            btn.disabled = false;
        }
    }

    async function startScan() {
        const tmNumbers = document.getElementById('tmInputScan').value.trim();
        const manualName = document.getElementById('manualNameInput').value.trim();

        // В БД результаты сохранятся по первому номеру
        currentScannedTM = tmNumbers.split(',')[0].trim();

        const btnStart = document.getElementById('btnStartScan');
        btnStart.disabled = true;
        btnStart.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Сканирование...`;

        document.getElementById('progressCard').classList.remove('d-none');
        document.getElementById('currentResultsCard').classList.add('d-none');
        resetProgressUI();

        try {
            // Передаем manual_name как query параметр
            let url = `${API_BASE_URL}/scan/${tmNumbers}`;
            if (manualName) {
                url += `?manual_name=${encodeURIComponent(manualName)}`;
            }

            const res = await fetch(url, { method: 'POST' });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail);
            }

            pollInterval = setInterval(checkStatus, 1000);

        } catch (error) {
            alert(error.message);
            btnStart.disabled = false;
            btnStart.innerHTML = `<i class="bi bi-play-circle"></i> Запустить сканирование`;
            document.getElementById('progressCard').classList.add('d-none');
        }
    }

    async function checkStatus() {
        try {
            const res = await fetch(`${API_BASE_URL}/status`);
            const data = await res.json();

            // Обновляем UI стадий
            updateStageUI('parsing', data.stages.parsing);
            updateStageUI('generating', data.stages.generating);
            updateStageUI('scraping', data.stages.scraping);
            updateStageUI('analyzing', data.stages.analyzing);
            updateStageUI('classifying', data.stages.classifying);
            updateStageUI('reporting', data.stages.reporting);

            // Если процесс завершился
            if (data.is_running === false) {
                clearInterval(pollInterval);

                // Восстанавливаем кнопку
                const btnStart = document.getElementById('btnStartScan');
                btnStart.disabled = false;
                btnStart.innerHTML = `<i class="bi bi-play-circle"></i> Запустить сканирование`;

                document.getElementById('scanStatusBadge').className = "badge bg-success";
                document.getElementById('scanStatusBadge').innerText = "Завершено!";

                // Загружаем результаты
                loadCurrentResults(currentScannedTM);
            }
        } catch (error) {
            console.error("Ошибка поллинга:", error);
        }
    }

    function updateStageUI(stageId, status) {
        const el = document.getElementById(`stage-${stageId}`);
        if (status === 'pending') {
            el.className = 'list-group-item stage-pending';
            el.innerHTML = `<i class="bi bi-circle"></i> ${el.innerText}`;
        } else if (status === 'running') {
            el.className = 'list-group-item stage-running';
            el.innerHTML = `<span class="spinner-border spinner-border-sm text-primary"></span> ${el.innerText}`;
        } else if (status === 'done') {
            el.className = 'list-group-item stage-done';
            el.innerHTML = `<i class="bi bi-check-circle-fill"></i> ${el.innerText}`;
        }
    }

    function resetProgressUI() {
        document.getElementById('scanStatusBadge').className = "badge bg-warning text-dark";
        document.getElementById('scanStatusBadge').innerText = "В процессе...";
        ['parsing', 'generating', 'scraping', 'analyzing', 'classifying', 'reporting'].forEach(s => updateStageUI(s, 'pending'));
    }

    async function loadCurrentResults(tmNumber) {
        try {
            const res = await fetch(`${API_BASE_URL}/results/${tmNumber}?latest=true`);
            if (!res.ok) throw new Error("Ошибка загрузки результатов");

            const data = await res.json();

            const tbody = document.querySelector('#currentResultsTable tbody');
            tbody.innerHTML = '';

            if (data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Новых результатов не найдено.</td></tr>`;
                document.getElementById('currentResultsCard').classList.remove('d-none');
                return;
            }

            data.forEach(item => {
                // Кодируем item ВНУТРИ цикла
                const itemBase64 = btoa(unescape(encodeURIComponent(JSON.stringify(item))));

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${item.id}</td>
                    <td><a href="${item.url}" target="_blank" class="text-decoration-none fw-bold">${item.domain_name}</a></td>
                    <td><span class="badge ${getBadgeClass(item.predicted_category)} fs-6">${item.predicted_category}</span></td>
                    <td>${item.confidence ? (item.confidence * 100).toFixed(0) + '%' : '-'}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="showDetails('${itemBase64}')">
                            <i class="bi bi-info-circle"></i> Детали
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });

            // Показываем карточку с результатами
            document.getElementById('currentResultsCard').classList.remove('d-none');
        } catch (error) {
            console.error("Ошибка в loadCurrentResults:", error);
        }
    }

    // --- ФУНКЦИЯ ПОКАЗА ДЕТАЛЕЙ ---

    function showDetails(encodedItemBase64) {
        let item;
        try {
            const jsonString = decodeURIComponent(escape(atob(encodedItemBase64)));
            item = JSON.parse(jsonString);
        } catch (e) {
            console.error("Ошибка декодирования данных:", e);
            alert("Не удалось открыть детали. Данные повреждены.");
            return;
        }

        document.getElementById('modalDomainTitle').innerText = `Анализ: ${item.url}`;

        const osint = item.features?.osint || {};
        const contacts = osint.contacts || {};
        const whois = osint.whois || {};
        const innData = osint.inn_validation || {};

        let osintHtml = `<p><strong>Администратор домена (WHOIS):</strong><br>${whois.registrant_org || 'Неизвестно'}</p>`;

        const phones = contacts.phones || [];
        if (phones.length > 0) {
            osintHtml += `<strong>Телефоны:</strong>`;
            phones.forEach(phone => {
                const googleLink = `https://www.google.com/search?q=${encodeURIComponent(phone)}`;
                osintHtml += `<br><a href="${googleLink}" target="_blank">${phone} </a>`;
            });
            osintHtml += `<br><br>`;
        }

        // --- Добавил вывод ИНН, чтобы в деталях было видно прозрачность бизнеса ---
        const inns = contacts.inn || [];
        if (inns.length > 0) {
            osintHtml += `<strong>ИНН:<br></strong> ${inns[0]} `;
            if (innData.exists) {
                const statusColor = innData.status === "ACTIVE" ? "success" : "danger";
                osintHtml += `<br>ФНС: ${innData.name}`;
                if (innData.address) {
                    osintHtml += `<br>${innData.address}`;
                }
                let statusText = ""
                if (innData.status == "ACTIVE") {statusText = "Активен"} else statusText = "Неактивен"
                osintHtml += `<br>Статус: <span class="badge bg-${statusColor}">${statusText}</span>`
            } else {
                osintHtml += `<span class="badge bg-danger">В реестре не найден!</span>`;
            }
            osintHtml += ` <br>`;
        }

        document.getElementById('modalOsintContent').innerHTML = osintHtml;

        const mlFeatures = { ...item.features };
        delete mlFeatures.osint; // Прячем OSINT из JSON, так как мы его вывели красиво выше
        document.getElementById('modalFeaturesJson').innerText = JSON.stringify(mlFeatures, null, 2);

        // Надежный вызов модального окна Bootstrap 5
        const modalElement = document.getElementById('detailsModal');
        let modalInstance = bootstrap.Modal.getInstance(modalElement);
        if (!modalInstance) {
            modalInstance = new bootstrap.Modal(modalElement);
        }
        modalInstance.show();
    }

    // --- ФУНКЦИИ ВКЛАДКИ ИСТОРИИ ---

    async function loadHistory() {
        const tmNumber = document.getElementById('tmInputHistory').value.trim();
        if (!tmNumber) return;

        const tbody = document.querySelector('#historyTable tbody');
        tbody.innerHTML = `<tr><td colspan="7" class="text-center"><span class="spinner-border text-primary"></span> Загрузка...</td></tr>`;

        try {
            const res = await fetch(`${API_BASE_URL}/results/${tmNumber}`);
            if (!res.ok) throw new Error("Нет данных");
            const data = await res.json();

            tbody.innerHTML = '';
            if (data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">История пуста.</td></tr>`;
                return;
            }

            data.forEach(item => {
                // 1. Кодируем весь объект для передачи в модальное окно
                const itemBase64 = btoa(unescape(encodeURIComponent(JSON.stringify(item))));

                // Форматируем дату красиво
                const dateStr = new Date(item.scan_date).toLocaleString('ru-RU', {
                    day: '2-digit', month: '2-digit', year: 'numeric',
                    hour: '2-digit', minute: '2-digit'
                });

                // 2. Отрисовываем строку с кнопкой "Детали"
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${item.id}</td>
                    <td><a href="${item.url}" target="_blank" class="text-decoration-none fw-bold">${item.domain_name}</a></td>
                    <td><span class="badge ${getBadgeClass(item.predicted_category)} fs-6">${item.predicted_category}</span></td>
                    <td>${item.confidence ? (item.confidence * 100).toFixed(0) + '%' : '-'}</td>
                    <td class="text-muted small">${dateStr}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="showDetails('${itemBase64}')">
                            <i class="bi bi-info-circle"></i> Детали
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } catch (error) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">${error.message}</td></tr>`;
        }
    }

    function getBadgeClass(category) {
        if (category === 'Нарушение') return 'badge-violation';
        if (category === 'Легальный') return 'badge-legal';
        if (category === 'Парковка') return 'badge-parking';
        return 'badge-suspicious';
    }