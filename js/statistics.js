/**
 * CESM Status Board - Statistics Visualization Module
 *
 * Manages the statistics tab for visualizing AMWG diagnostic metrics
 */
class StatisticsManager {
    constructor(app) {
        this.app = app;  // Reference to CESMStatusBoard instance
        this.state = {
            selectedVariable: null,
            selectedMetric: 'global_mean',
            selectedPeriods: [],  // Populated dynamically from data
            viewMode: 'table',  // 'table' or 'chart'
            chartType: 'bar'  // 'bar' or 'line'
        };
        this.selectedCases = new Set();  // case_names to include; empty = show all
        this.chart = null;  // Chart.js instance
        this.availableVariables = [];
        this.availablePeriods = [];  // All periods found in data
        this.initialized = false;
    }

    /**
     * Initialize the statistics manager
     */
    init() {
        if (this.initialized) return;

        console.log('Initializing Statistics Manager...');

        this.discoverVariables();
        this.initCaseSelector();
        this.renderControls();
        this.setupEventListeners();
        this.updateView();

        this.initialized = true;
        console.log('Statistics Manager initialized');
    }

    /**
     * Scan all cases to find unique variable names and temporal periods
     */
    discoverVariables() {
        const variables = new Set();
        const periods = new Set();

        this.app.cases.forEach(caseData => {
            if (caseData.statistics && caseData.has_diagnostics) {
                Object.entries(caseData.statistics).forEach(([periodKey, vars]) => {
                    periods.add(periodKey);
                    Object.keys(vars).forEach(varName => variables.add(varName));
                });
            }
        });

        this.availableVariables = Array.from(variables).sort();
        this.availablePeriods = Array.from(periods).sort();

        // Default: select all discovered periods
        this.state.selectedPeriods = [...this.availablePeriods];

        // Set default variable
        if (this.availableVariables.length > 0) {
            this.state.selectedVariable = this.availableVariables[0];
        }

        console.log(`Discovered ${this.availableVariables.length} variables, ${this.availablePeriods.length} periods:`, this.availablePeriods);
    }

    /**
     * Render control elements
     */
    renderControls() {
        // Populate variable dropdown
        const variableSelect = document.getElementById('variableSelect');
        variableSelect.innerHTML = '';

        if (this.availableVariables.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No variables available';
            variableSelect.appendChild(option);
            return;
        }

        this.availableVariables.forEach(varName => {
            const option = document.createElement('option');
            option.value = varName;
            option.textContent = varName;
            variableSelect.appendChild(option);
        });

        // Set selected variable
        if (this.state.selectedVariable) {
            variableSelect.value = this.state.selectedVariable;
        }

        // Set selected metric
        document.getElementById('metricSelect').value = this.state.selectedMetric;

        // Populate dynamic period checkboxes for any period not in the standard set
        const standardPeriods = new Set(['ANN', 'DJF', 'MAM', 'JJA', 'SON',
            'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']);

        const extraPeriods = this.availablePeriods.filter(p => !standardPeriods.has(p));
        const container = document.getElementById('extraPeriods');
        if (container) {
            container.innerHTML = '';
            extraPeriods.forEach(period => {
                const label = document.createElement('label');
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.className = 'period-checkbox';
                checkbox.value = period;
                checkbox.checked = true;
                label.appendChild(checkbox);
                label.appendChild(document.createTextNode('\u00a0' + period));
                container.appendChild(label);
            });
            if (extraPeriods.length > 0) {
                container.style.display = 'flex';
            }
        }
    }

    /**
     * Setup event listeners for controls
     */
    setupEventListeners() {
        // Variable selection
        document.getElementById('variableSelect').addEventListener('change', (e) => {
            this.state.selectedVariable = e.target.value;
            this.updateView();
        });

        // Metric selection
        document.getElementById('metricSelect').addEventListener('change', (e) => {
            this.state.selectedMetric = e.target.value;
            this.updateView();
        });

        // Period checkboxes
        document.querySelectorAll('.period-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                this.updateSelectedPeriods();
                this.updateView();
            });
        });

        // Show/hide monthly periods
        document.getElementById('showMonthly').addEventListener('click', () => {
            const monthlyDiv = document.getElementById('monthlyPeriods');
            const btn = document.getElementById('showMonthly');

            if (monthlyDiv.style.display === 'none') {
                monthlyDiv.style.display = 'flex';
                btn.textContent = '− Monthly';
            } else {
                monthlyDiv.style.display = 'none';
                btn.textContent = '+ Monthly';
            }
        });

        // View mode toggle
        document.getElementById('tableViewBtn').addEventListener('click', () => {
            this.setViewMode('table');
        });

        document.getElementById('chartViewBtn').addEventListener('click', () => {
            this.setViewMode('chart');
        });

        // Refresh button
        document.getElementById('refreshStats').addEventListener('click', () => {
            this.updateView();
        });
    }

    /**
     * Update selected periods from checkboxes
     */
    updateSelectedPeriods() {
        const checkedBoxes = document.querySelectorAll('.period-checkbox:checked');
        this.state.selectedPeriods = Array.from(checkedBoxes).map(cb => cb.value);
    }

    /**
     * Set view mode (table or chart)
     */
    setViewMode(mode) {
        this.state.viewMode = mode;

        // Update button states
        const tableBtn = document.getElementById('tableViewBtn');
        const chartBtn = document.getElementById('chartViewBtn');

        if (mode === 'table') {
            tableBtn.classList.add('active');
            chartBtn.classList.remove('active');
        } else {
            tableBtn.classList.remove('active');
            chartBtn.classList.add('active');
        }

        this.updateView();
    }

    /**
     * Build the case selector list and wire its controls
     */
    initCaseSelector() {
        const diagCases = this.app.cases.filter(c => c.has_diagnostics);

        // Start with all cases selected
        diagCases.forEach(c => this.selectedCases.add(c.case_name));

        this._renderStatsCaseRows(diagCases);
        this._updateCaseSelectorCount();

        document.getElementById('statsCaseSearch').addEventListener('input', (e) => {
            this._filterStatsCaseList(e.target.value.toLowerCase());
        });

        document.getElementById('statsSelectAll').addEventListener('click', () => {
            // Select ALL cases regardless of current filter
            const list = document.getElementById('statsCaseList');
            list.querySelectorAll('.stats-case-cb').forEach(cb => {
                cb.checked = true;
                this.selectedCases.add(cb.value);
            });
            this._updateCaseSelectorCount();
            this.updateView();
        });

        document.getElementById('statsClearSelected').addEventListener('click', () => {
            // Deselect all cases regardless of filter
            const list = document.getElementById('statsCaseList');
            list.querySelectorAll('.stats-case-cb').forEach(cb => {
                cb.checked = false;
            });
            this.selectedCases.clear();
            this._updateCaseSelectorCount();
            this.updateView();
        });
    }

    /**
     * Render case rows into the selector list using createElement (avoids innerHTML
     * fragility with arbitrary case name strings).
     */
    _renderStatsCaseRows(cases) {
        const list = document.getElementById('statsCaseList');
        if (!list) return;
        list.innerHTML = '';

        if (cases.length === 0) {
            const msg = document.createElement('p');
            msg.style.cssText = 'padding:0.5rem;color:var(--text-secondary);font-size:0.85em;';
            msg.textContent = 'No cases with diagnostics found.';
            list.appendChild(msg);
            return;
        }

        cases.forEach(c => {
            // Use a div (not label) as the flex row — Safari collapses flex labels
            const row = document.createElement('div');
            row.className = 'stats-case-row';
            row.dataset.caseName = c.case_name;

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.id = `stats-cb-${CSS.escape(c.case_name)}`;
            cb.className = 'stats-case-cb';
            cb.value = c.case_name;
            cb.checked = this.selectedCases.has(c.case_name);
            cb.addEventListener('change', () => {
                if (cb.checked) {
                    this.selectedCases.add(c.case_name);
                } else {
                    this.selectedCases.delete(c.case_name);
                }
                this._updateCaseSelectorCount();
                this.updateView();
            });

            // Label wraps the checkbox + name so clicking the name toggles it
            const lbl = document.createElement('label');
            lbl.htmlFor = cb.id;
            lbl.className = 'stats-case-label';

            const nameSpan = document.createElement('span');
            nameSpan.className = 'namelist-case-name';
            nameSpan.textContent = c.case_name;
            lbl.appendChild(nameSpan);

            row.appendChild(cb);
            row.appendChild(lbl);

            if (c.year_range) {
                const yr = document.createElement('span');
                yr.className = 'namelist-case-meta';
                yr.textContent = c.year_range;
                row.appendChild(yr);
            }
            if (c.issue_number) {
                const iss = document.createElement('span');
                iss.className = 'namelist-case-meta';
                iss.textContent = `#${c.issue_number}`;
                row.appendChild(iss);
            }

            list.appendChild(row);
        });
    }

    /**
     * Filter visible case rows in the selector by search string
     */
    _filterStatsCaseList(query) {
        const list = document.getElementById('statsCaseList');
        if (!list) return;
        list.querySelectorAll('.stats-case-row').forEach(row => {
            const name = row.dataset.caseName.toLowerCase();
            row.style.display = name.includes(query) ? '' : 'none';
        });
    }

    /**
     * Update the selected-count label
     */
    _updateCaseSelectorCount() {
        const total = this.app.cases.filter(c => c.has_diagnostics).length;
        const sel = this.selectedCases.size;
        const el = document.getElementById('statsCaseSelectedCount');
        if (el) el.textContent = `${sel} of ${total} selected`;
    }

    /**
     * Aggregate data for selected variable/metric/periods.
     *
     * @param {boolean} includeEmpty - When true (table view), include rows that have
     *   no data for the current variable so every selected case appears.
     *   When false (chart view), drop rows with no data to avoid empty bars.
     */
    aggregateData(includeEmpty = false) {
        const data = [];

        // Get cases with diagnostics, filtered by case selector
        const cases = this.app.cases.filter(c =>
            c.has_diagnostics &&
            (this.selectedCases.size === 0 || this.selectedCases.has(c.case_name))
        );

        cases.forEach(caseData => {
            const row = {
                caseId: caseData.id,
                caseName: caseData.case_name,
                caseNameShort: this.truncateCaseName(caseData.case_name)
            };

            // Collect values for each selected period
            this.state.selectedPeriods.forEach(period => {
                const value = caseData.statistics?.[period]?.[this.state.selectedVariable]?.[this.state.selectedMetric];
                row[period] = value !== undefined ? value : null;
            });

            const hasData = this.state.selectedPeriods.some(p => row[p] !== null);
            if (includeEmpty || hasData) {
                data.push(row);
            }
        });

        return data;
    }

    /**
     * Truncate case name for display
     */
    truncateCaseName(caseName, maxLength = 40) {
        if (caseName.length <= maxLength) return caseName;
        return caseName.substring(0, maxLength - 3) + '...';
    }

    /**
     * Main update function - renders current view
     */
    updateView() {
        if (!this.state.selectedVariable || this.state.selectedPeriods.length === 0) {
            this.showEmptyState();
            return;
        }

        // Table shows all selected cases (N/A for missing); chart drops empty rows
        const isTable = this.state.viewMode === 'table';
        const data = this.aggregateData(isTable);

        if (data.length === 0) {
            this.showEmptyState();
            return;
        }

        this.hideEmptyState();

        if (isTable) {
            this.renderTable(data);
            this.showTableView();
        } else {
            this.renderChart(data);
            this.showChartView();
        }
    }

    /**
     * Show empty state message
     */
    showEmptyState() {
        document.getElementById('statsEmptyState').style.display = 'block';
        document.getElementById('statisticsTableContainer').style.display = 'none';
        document.getElementById('statisticsChartContainer').style.display = 'none';
    }

    /**
     * Hide empty state message
     */
    hideEmptyState() {
        document.getElementById('statsEmptyState').style.display = 'none';
    }

    /**
     * Show table view
     */
    showTableView() {
        document.getElementById('statisticsTableContainer').style.display = 'block';
        document.getElementById('statisticsChartContainer').style.display = 'none';
    }

    /**
     * Show chart view
     */
    showChartView() {
        document.getElementById('statisticsTableContainer').style.display = 'none';
        document.getElementById('statisticsChartContainer').style.display = 'block';
    }

    /**
     * Render table view
     */
    renderTable(data) {
        const table = document.getElementById('statisticsTable');

        // Build header
        let headerHTML = '<thead><tr><th>Case Name</th>';
        this.state.selectedPeriods.forEach(period => {
            headerHTML += `<th>${period}</th>`;
        });
        headerHTML += '</tr></thead>';

        // Build body
        let bodyHTML = '<tbody>';
        data.forEach(row => {
            bodyHTML += '<tr>';
            bodyHTML += `<td class="case-name-cell" title="${row.caseName}">${row.caseNameShort}</td>`;

            this.state.selectedPeriods.forEach(period => {
                const value = row[period];
                if (value !== null && value !== undefined) {
                    bodyHTML += `<td class="value-cell">${this.formatValue(value)}</td>`;
                } else {
                    bodyHTML += `<td class="value-cell missing">N/A</td>`;
                }
            });

            bodyHTML += '</tr>';
        });
        bodyHTML += '</tbody>';

        table.innerHTML = headerHTML + bodyHTML;
    }

    /**
     * Format numeric value for display
     */
    formatValue(value) {
        if (typeof value !== 'number') return value;

        // Format based on magnitude
        if (Math.abs(value) >= 100) {
            return value.toFixed(1);
        } else if (Math.abs(value) >= 1) {
            return value.toFixed(2);
        } else if (Math.abs(value) >= 0.01) {
            return value.toFixed(3);
        } else {
            return value.toExponential(2);
        }
    }

    /**
     * Get metric label for display
     */
    getMetricLabel(metric) {
        const labels = {
            'global_mean': 'Global Mean',
            'rmse': 'RMSE',
            'bias': 'Bias',
            'std': 'Standard Deviation'
        };
        return labels[metric] || metric;
    }

    /**
     * Get color for period
     */
    getPeriodColor(period, alpha = 1) {
        const colors = {
            'ANN': `rgba(37, 99, 235, ${alpha})`,     // Blue
            'DJF': `rgba(124, 58, 237, ${alpha})`,    // Purple (winter)
            'MAM': `rgba(16, 185, 129, ${alpha})`,    // Green (spring)
            'JJA': `rgba(245, 158, 11, ${alpha})`,    // Orange (summer)
            'SON': `rgba(239, 68, 68, ${alpha})`,     // Red (fall)
            'Jan': `rgba(96, 125, 139, ${alpha})`,    // Blue-grey
            'Feb': `rgba(121, 134, 203, ${alpha})`,
            'Mar': `rgba(129, 212, 250, ${alpha})`,
            'Apr': `rgba(102, 187, 106, ${alpha})`,
            'May': `rgba(156, 204, 101, ${alpha})`,
            'Jun': `rgba(255, 241, 118, ${alpha})`,
            'Jul': `rgba(255, 183, 77, ${alpha})`,
            'Aug': `rgba(255, 138, 101, ${alpha})`,
            'Sep': `rgba(240, 98, 146, ${alpha})`,
            'Oct': `rgba(206, 147, 216, ${alpha})`,
            'Nov': `rgba(149, 117, 205, ${alpha})`,
            'Dec': `rgba(100, 181, 246, ${alpha})`
        };
        return colors[period] || `rgba(156, 163, 175, ${alpha})`;
    }

    /**
     * Render chart view
     */
    renderChart(data) {
        // Destroy existing chart
        if (this.chart) {
            this.chart.destroy();
        }

        const ctx = document.getElementById('statisticsChart').getContext('2d');

        // Prepare datasets (one per period)
        const datasets = this.state.selectedPeriods.map((period, index) => {
            return {
                label: period,
                data: data.map(row => row[period]),
                backgroundColor: this.getPeriodColor(period, 0.7),
                borderColor: this.getPeriodColor(period, 1),
                borderWidth: 1
            };
        });

        // Case labels (truncated)
        const labels = data.map(row => row.caseNameShort);

        // Full case names for tooltips
        const fullNames = data.map(row => row.caseName);

        const config = {
            type: 'bar',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            font: {
                                size: 12
                            }
                        }
                    },
                    title: {
                        display: true,
                        text: `${this.state.selectedVariable} - ${this.getMetricLabel(this.state.selectedMetric)}`,
                        font: {
                            size: 16,
                            weight: 'bold'
                        }
                    },
                    tooltip: {
                        callbacks: {
                            title: (context) => {
                                const index = context[0].dataIndex;
                                return fullNames[index];
                            },
                            label: (context) => {
                                const value = context.parsed.y;
                                if (value === null) return `${context.dataset.label}: N/A`;
                                return `${context.dataset.label}: ${this.formatValue(value)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            font: {
                                size: 10
                            },
                            maxRotation: 45,
                            minRotation: 45
                        }
                    },
                    y: {
                        beginAtZero: false,
                        title: {
                            display: true,
                            text: this.getMetricLabel(this.state.selectedMetric),
                            font: {
                                size: 12,
                                weight: 'bold'
                            }
                        },
                        ticks: {
                            font: {
                                size: 11
                            }
                        }
                    }
                }
            }
        };

        this.chart = new Chart(ctx, config);
    }
}

// Make StatisticsManager available globally
window.StatisticsManager = StatisticsManager;
