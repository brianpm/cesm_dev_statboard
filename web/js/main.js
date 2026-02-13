/**
 * CESM Status Board - Main Application
 */
class CESMStatusBoard {
    constructor() {
        this.cases = [];
        this.filteredCases = [];
        this.statistics = {};
        this.currentPage = 1;
        this.itemsPerPage = 50;
        this.sortColumn = 'case_name';
        this.sortDirection = 'asc';
        this.statisticsManager = null;
        this.currentTab = 'cases';
    }

    async init() {
        console.log('Initializing CESM Status Board...');

        try {
            await this.loadData();
            this.setupEventListeners();
            this.renderDashboard();
            this.renderFilters();
            this.renderTable();
            this.hideLoading();

            // Initialize Statistics Manager
            this.statisticsManager = new StatisticsManager(this);
            window.statisticsManager = this.statisticsManager;

            // Check if we should show statistics tab on load
            if (window.location.hash === '#statistics') {
                this.switchTab('statistics');
            }

            console.log('Initialization complete');
        } catch (error) {
            console.error('Initialization error:', error);
            this.showError('Failed to load data. Please try again later.');
        }
    }

    async loadData() {
        console.log('Loading data...');

        try {
            // Load cases
            const casesResponse = await fetch('data/cases.json');
            const casesData = await casesResponse.json();
            this.cases = casesData.cases || [];

            console.log(`Loaded ${this.cases.length} cases`);

            // Load statistics
            const statsResponse = await fetch('data/statistics.json');
            this.statistics = await statsResponse.json();

            // Load last update info
            const updateResponse = await fetch('data/last_update.json');
            const updateData = await updateResponse.json();

            // Update last update timestamp
            this.updateLastUpdateDisplay(updateData);

            // Initialize filtered cases
            this.filteredCases = [...this.cases];

        } catch (error) {
            console.error('Error loading data:', error);
            throw error;
        }
    }

    setupEventListeners() {
        // Tab navigation
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.switchTab(btn.dataset.tab);
            });
        });

        // Sort table headers
        document.querySelectorAll('.sortable').forEach(header => {
            header.addEventListener('click', () => {
                const column = header.dataset.sort;
                this.sortTable(column);
            });
        });

        // Pagination
        document.getElementById('prevPage').addEventListener('click', () => this.previousPage());
        document.getElementById('nextPage').addEventListener('click', () => this.nextPage());

        // Compare mode toggle
        document.getElementById('toggleCompareMode').addEventListener('click', () => {
            window.comparisonTool.toggleCompareMode();
        });

        // Modal close
        document.querySelectorAll('.close').forEach(closeBtn => {
            closeBtn.addEventListener('click', () => {
                document.querySelectorAll('.modal').forEach(modal => {
                    modal.style.display = 'none';
                });
            });
        });

        // Click outside modal to close
        window.addEventListener('click', (event) => {
            if (event.target.classList.contains('modal')) {
                event.target.style.display = 'none';
            }
        });
    }

    renderDashboard() {
        const totalCases = this.cases.length;
        const withDiagnostics = this.cases.filter(c => c.has_diagnostics).length;
        const coverage = totalCases > 0 ? Math.round(withDiagnostics / totalCases * 100) : 0;
        const uniqueCompsets = new Set(this.cases.map(c => c.compset).filter(Boolean)).size;

        document.getElementById('totalCases').textContent = totalCases.toLocaleString();
        document.getElementById('withDiagnostics').textContent = withDiagnostics.toLocaleString();
        document.getElementById('diagnosticCoverage').textContent = `${coverage}%`;
        document.getElementById('uniqueCompsets').textContent = uniqueCompsets;
    }

    renderFilters() {
        // Populate compset filter
        const compsets = [...new Set(this.cases.map(c => c.compset).filter(Boolean))].sort();
        const compsetFilter = document.getElementById('compsetFilter');

        compsets.forEach(compset => {
            const option = document.createElement('option');
            option.value = compset;
            option.textContent = compset;
            compsetFilter.appendChild(option);
        });

        // Populate resolution filter
        const resolutions = [...new Set(this.cases.map(c => c.resolution).filter(Boolean))].sort();
        const resolutionFilter = document.getElementById('resolutionFilter');

        resolutions.forEach(resolution => {
            const option = document.createElement('option');
            option.value = resolution;
            option.textContent = resolution;
            resolutionFilter.appendChild(option);
        });
    }

    renderTable() {
        const start = (this.currentPage - 1) * this.itemsPerPage;
        const end = start + this.itemsPerPage;
        const pageData = this.filteredCases.slice(start, end);

        const tbody = document.getElementById('caseTableBody');
        tbody.innerHTML = '';

        pageData.forEach(caseData => {
            const row = this.createTableRow(caseData);
            tbody.appendChild(row);
        });

        // Update case count
        document.getElementById('caseCount').textContent = `(${this.filteredCases.length})`;

        // Update pagination
        this.updatePagination();
    }

    createTableRow(caseData) {
        const row = document.createElement('tr');

        // Checkbox column
        const checkboxCell = document.createElement('td');
        checkboxCell.className = 'checkbox-col';
        if (window.comparisonTool && window.comparisonTool.compareMode) {
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.dataset.caseId = caseData.id;
            checkbox.addEventListener('change', (e) => {
                window.comparisonTool.toggleCaseSelection(caseData.id, e.target.checked);
            });
            checkboxCell.appendChild(checkbox);
        }
        row.appendChild(checkboxCell);

        // Case name
        const nameCell = document.createElement('td');
        nameCell.textContent = caseData.case_name || 'Unknown';
        nameCell.style.fontFamily = 'monospace';
        nameCell.style.fontSize = '0.9em';
        row.appendChild(nameCell);

        // Compset
        const compsetCell = document.createElement('td');
        compsetCell.textContent = caseData.compset || '-';
        row.appendChild(compsetCell);

        // Resolution
        const resolutionCell = document.createElement('td');
        resolutionCell.textContent = caseData.resolution || '-';
        row.appendChild(resolutionCell);

        // Status
        const statusCell = document.createElement('td');
        const statusBadge = document.createElement('span');
        statusBadge.className = `badge ${caseData.issue_state === 'open' ? 'badge-open' : 'badge-closed'}`;
        statusBadge.textContent = caseData.issue_state || 'unknown';
        statusCell.appendChild(statusBadge);
        row.appendChild(statusCell);

        // Diagnostics
        const diagCell = document.createElement('td');
        const diagBadge = document.createElement('span');
        diagBadge.className = `badge ${caseData.has_diagnostics ? 'badge-success' : 'badge-warning'}`;
        diagBadge.textContent = caseData.has_diagnostics ? 'Yes' : 'Pending';
        diagCell.appendChild(diagBadge);
        row.appendChild(diagCell);

        // Purpose (truncated)
        const purposeCell = document.createElement('td');
        const purpose = caseData.purpose || '-';
        purposeCell.textContent = purpose.length > 60 ? purpose.substring(0, 60) + '...' : purpose;
        purposeCell.style.maxWidth = '300px';
        row.appendChild(purposeCell);

        // Actions
        const actionsCell = document.createElement('td');
        const viewBtn = document.createElement('button');
        viewBtn.className = 'btn-view';
        viewBtn.textContent = 'View';
        viewBtn.addEventListener('click', () => this.showCaseDetail(caseData));
        actionsCell.appendChild(viewBtn);
        row.appendChild(actionsCell);

        return row;
    }

    showCaseDetail(caseData) {
        const modal = document.getElementById('caseModal');
        const detailDiv = document.getElementById('caseDetail');

        let html = `
            <h2>${caseData.case_name}</h2>

            <div class="detail-section">
                <h3>Configuration</h3>
                <p><strong>Compset:</strong> ${caseData.compset || 'N/A'}</p>
                <p><strong>Resolution:</strong> ${caseData.resolution || 'N/A'}</p>
                <p><strong>Experiment ID:</strong> ${caseData.experiment_id || 'N/A'}</p>
                <p><strong>Case Number:</strong> ${caseData.case_number || 'N/A'}</p>
            </div>

            <div class="detail-section">
                <h3>Status</h3>
                <p><strong>Issue State:</strong> <span class="badge ${caseData.issue_state === 'open' ? 'badge-open' : 'badge-closed'}">${caseData.issue_state || 'unknown'}</span></p>
                <p><strong>Diagnostics:</strong> <span class="badge ${caseData.has_diagnostics ? 'badge-success' : 'badge-warning'}">${caseData.has_diagnostics ? 'Available' : 'Pending'}</span></p>
                <p><strong>GitHub Issue:</strong> <a href="https://github.com/NCAR/cesm_dev/issues/${caseData.issue_number}" target="_blank">#${caseData.issue_number}</a></p>
            </div>

            <div class="detail-section">
                <h3>Purpose</h3>
                <p>${caseData.purpose || 'Not specified'}</p>
            </div>

            <div class="detail-section">
                <h3>Description</h3>
                <p>${caseData.description || 'Not specified'}</p>
            </div>

            <div class="detail-section">
                <h3>Filesystem Paths</h3>
                <p><strong>Case Directory:</strong> ${caseData.case_directory || 'Not found'}</p>
                <p><strong>Diagnostics Directory:</strong> ${caseData.diagnostics_directory || 'Not found'}</p>
            </div>
        `;

        // Add statistics if available
        if (caseData.statistics && Object.keys(caseData.statistics).length > 0) {
            html += '<div class="detail-section"><h3>Statistics Summary</h3>';
            for (const [period, variables] of Object.entries(caseData.statistics)) {
                const varCount = Object.keys(variables).length;
                html += `<p><strong>${period}:</strong> ${varCount} variables</p>`;
            }
            html += '</div>';
        }

        // Add contacts if available
        if (caseData.contacts && caseData.contacts.length > 0) {
            html += `<div class="detail-section">
                <h3>Contacts</h3>
                <p>${caseData.contacts.map(c => `@${c}`).join(', ')}</p>
            </div>`;
        }

        detailDiv.innerHTML = html;
        modal.style.display = 'block';
    }

    sortTable(column) {
        if (this.sortColumn === column) {
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortColumn = column;
            this.sortDirection = 'asc';
        }

        this.filteredCases.sort((a, b) => {
            let aVal = a[column] || '';
            let bVal = b[column] || '';

            if (typeof aVal === 'string') {
                aVal = aVal.toLowerCase();
                bVal = bVal.toLowerCase();
            }

            if (aVal < bVal) return this.sortDirection === 'asc' ? -1 : 1;
            if (aVal > bVal) return this.sortDirection === 'asc' ? 1 : -1;
            return 0;
        });

        this.renderTable();
    }

    updatePagination() {
        const totalPages = Math.ceil(this.filteredCases.length / this.itemsPerPage);

        document.getElementById('prevPage').disabled = this.currentPage === 1;
        document.getElementById('nextPage').disabled = this.currentPage >= totalPages;
        document.getElementById('pageInfo').textContent = `Page ${this.currentPage} of ${totalPages}`;
    }

    previousPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.renderTable();
        }
    }

    nextPage() {
        const totalPages = Math.ceil(this.filteredCases.length / this.itemsPerPage);
        if (this.currentPage < totalPages) {
            this.currentPage++;
            this.renderTable();
        }
    }

    updateFilteredCases(filteredCases) {
        this.filteredCases = filteredCases;
        this.currentPage = 1;
        this.renderTable();
    }

    hideLoading() {
        document.getElementById('loading').style.display = 'none';
    }

    showError(message) {
        const loading = document.getElementById('loading');
        loading.textContent = message;
        loading.style.color = 'var(--danger-color)';
    }

    updateLastUpdateDisplay(updateData) {
        const timestamp = new Date(updateData.timestamp);
        const formatted = timestamp.toLocaleString();

        document.getElementById('lastUpdate').textContent = `Last updated: ${formatted}`;
        document.getElementById('footerLastUpdate').textContent = formatted;
    }

    /**
     * Switch between tabs
     */
    switchTab(tabName) {
        console.log(`Switching to tab: ${tabName}`);

        // Update current tab
        this.currentTab = tabName;

        // Update tab button states
        document.querySelectorAll('.tab-btn').forEach(btn => {
            if (btn.dataset.tab === tabName) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        // Update tab content visibility
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });

        const targetTab = document.getElementById(`${tabName}Tab`);
        if (targetTab) {
            targetTab.classList.add('active');
        }

        // Update URL hash
        window.location.hash = `#${tabName}`;

        // Initialize statistics manager when switching to statistics tab
        if (tabName === 'statistics' && this.statisticsManager) {
            this.statisticsManager.init();
        }
    }

    /**
     * Switch to statistics tab and optionally filter by case name
     */
    switchToStatsTab(caseName = null) {
        this.switchTab('statistics');

        if (caseName && this.statisticsManager) {
            // Could add filtering by case name here in the future
            console.log(`Showing statistics for case: ${caseName}`);
        }
    }
}
