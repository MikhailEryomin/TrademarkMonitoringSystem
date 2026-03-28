const API_BASE_URL = "http://localhost:8000/api";
    let pollInterval = null;
    let currentScannedTM = null;

    // --- ФУНКЦИИ ВКЛАДКИ СКАНИРОВАНИЯ ---

    async function fetchTMInfo() {
        const tmNumber = document.getElementById('tmInputScan').value.trim();
        if (!tmNumber) return alert("Введите номер ТЗ");

        const btn = document.getElementById('btnFindTM');
        btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Ищем...`;
        btn.disabled = true;

        try {
            const res = await fetch(`${API_BASE_URL}/trademark/${tmNumber}`);
            if (!res.ok) throw new Error("ТЗ не найден или ошибка сервера");
            const data = await res.json();

            // Заполняем карточку
            document.getElementById('tmLogo').src = data.logo_url;
            document.getElementById('tmName').innerText = `${data.name} (${data.name_lat})`;
            document.getElementById('tmOwner').innerText = data.owner_name;
            document.getElementById('tmClasses').innerText = data.mktu_nums.join(', ');

            // Показываем карточку и кнопку запуска
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
        const tmNumber = document.getElementById('tmInputScan').value.trim();
        currentScannedTM = tmNumber;

        // Блокируем кнопку и показываем панель прогресса
        const btnStart = document.getElementById('btnStartScan');
        btnStart.disabled = true;
        btnStart.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Сканирование...`;

        document.getElementById('progressCard').classList.remove('d-none');
        document.getElementById('currentResultsCard').classList.add('d-none');
        resetProgressUI();

        try {
            const res = await fetch(`${API_BASE_URL}/scan/${tmNumber}`, { method: 'POST' });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail);
            }

            // Начинаем поллинг статуса каждую секунду
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
            const res = await fetch(`${API_BASE_URL}/results/${tmNumber}`);
            const data = await res.json();

            const tbody = document.querySelector('#currentResultsTable tbody');
            tbody.innerHTML = '';

            data.forEach(item => {
                const itemJson = encodeURIComponent(JSON.stringify(item));
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${item.id}</td>
                    <td><a href="${item.url}" target="_blank" class="text-decoration-none fw-bold">${item.domain_name}</a></td>
                    <td><span class="badge ${getBadgeClass(item.predicted_category)} fs-6">${item.predicted_category}</span></td>
                    <td>${item.confidence ? (item.confidence * 100).toFixed(0) + '%' : '-'}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="showDetails('${itemJson}')">
                            <i class="bi bi-info-circle"></i>
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });

            document.getElementById('currentResultsCard').classList.remove('d-none');
        } catch (error) {
            console.error(error);
        }
    }

// --- ФУНКЦИЯ ПОКАЗА ДЕТАЛЕЙ ---

    function showDetails(encodedItem) {
        const item = JSON.parse(decodeURIComponent(encodedItem));
        document.getElementById('modalDomainTitle').innerText = `Анализ: ${item.url}`;

        // 1. Достаем наш блок OSINT
        const osint = item.features?.osint || {};
        const contacts = osint.contacts || {};
        const whois = osint.whois || {};
        const innData = osint.inn_validation || {};

        let osintHtml = "";

        // --- WHOIS ---
        osintHtml += `<p><strong>Владелец домена (WHOIS):</strong><br>
                      ${whois.registrant_org || 'Неизвестно'}
                      ${whois.is_private ? '<span class="badge bg-warning text-dark">Скрыт (Private)</span>' : ''}</p>`;

        // --- ТЕЛЕФОНЫ (С поиском в Google) ---
        const phones = contacts.phones || [];
        if (phones.length > 0) {
            osintHtml += `<strong>Телефоны:</strong><ul>`;
            phones.forEach(phone => {
                // Кодируем номер для гугла (например %2B7999...)
                const googleLink = `https://www.google.com/search?q="${encodeURIComponent(phone)}"`;
                osintHtml += `<li><a href="${googleLink}" target="_blank" class="text-decoration-none">${phone} 🔍</a></li>`;
            });
            osintHtml += `</ul>`;
        } else {
            osintHtml += `<p><strong>Телефоны:</strong> Не найдены</p>`;
        }

        // --- ЕМЕЙЛЫ ---
        const emails = contacts.emails || [];
        if (emails.length > 0) {
            osintHtml += `<strong>Email:</strong> ${emails.join(', ')}<br><br>`;
        }

        // --- ИНН и DADATA ---
        const inns = contacts.inn || [];
        if (inns.length > 0) {
            osintHtml += `<strong>ИНН на сайте:</strong> ${inns[0]} `;
            if (innData.exists) {
                const statusColor = innData.status === "ACTIVE" ? "success" : "danger";
                osintHtml += `<br><em>ФНС: ${innData.name}</em> <span class="badge bg-${statusColor}">${innData.status}</span>`;
                osintHtml += `<br><small class="text-muted">${innData.address}</small>`;
            } else {
                osintHtml += `<span class="badge bg-danger">В реестре не найден!</span>`;
            }
            osintHtml += ` <br>`;
        }

        document.getElementById('modalOsintContent').innerHTML = osintHtml;

        // 2. Вставляем чистые ML-признаки (убрав блок osint, чтобы не мусорить на экране)
        const mlFeatures = { ...item.features };
        delete mlFeatures.osint; // Удаляем из отображения JSON, т.к. мы уже отрисовали это выше
        document.getElementById('modalFeaturesJson').innerText = JSON.stringify(mlFeatures, null, 2);

        // 3. Показываем модальное окно
        const modal = new bootstrap.Modal(document.getElementById('detailsModal'));
        modal.show();
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
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${item.id}</td>
                    <td class="fw-bold">${item.domain_name}</td>
                    <td><a href="${item.url}" target="_blank">${item.url}</a></td>
                    <td><span class="badge ${getBadgeClass(item.predicted_category)}">${item.predicted_category}</span></td>
                    <td>${item.confidence ? (item.confidence * 100).toFixed(0) + '%' : '-'}</td>
                    <td>${item.domain_similarity ? item.domain_similarity.toFixed(2) : '-'}</td>
                    <td class="text-muted small">${new Date(item.scan_date).toLocaleString('ru-RU')}</td>
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