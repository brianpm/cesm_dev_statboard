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
            selectedPeriods: ['ANN', 'DJF', 'MAM', 'JJA', 'SON'],
            filterCases: [],  // Empty = all cases with diagnostics
            viewMode: 'table',  // 'table' or 'chart'
            chartType: 'bar'  // 'bar' or 'line'
        };
        this.chart = null;  // Chart.js instance
        this.availableVariables = [];
        this.initialized = false;
    }

    /**
     * Initialize the statistics manager
     */
    init() {
        if (this.initialized) return;

        console.log('Initializing Statistics Manager...');

        this.discoverVariables();
        this.renderControls();
        this.setupEventListeners();
        this.updateView();

        this.initialized = true;
        console.log('Statistics Manager initialized');
    }

    /**
     * Scan all cases to find unique variable names
     */
    discoverVariables() {
        const variables = new Set();

        this.app.cases.forEach(caseData => {
            if (caseData.statistics && caseData.has_diagnostics) {
                Object.values(caseData.statistics).forEach(period => {
                    Object.keys(period).forEach(varName => variables.add(varName));
                });
            }
        });

        this.availableVariables = Array.from(variables).sort();

        // Set default variable
        if (this.availableVariables.length > 0) {
            this.state.selectedVariable = this.availableVariables[0];
        }

        console.log(`Discovered ${this.availableVariables.length} unique variables`);
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
     * Aggregate data for selected variable/metric/periods
     */
    aggregateData() {
        const data = [];

        // Get cases with diagnostics
        const cases = this.app.cases.filter(c => c.has_diagnostics);

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

            // Only include rows that have at least one value
            const hasData = this.state.selectedPeriods.some(p => row[p] !== null);
            if (hasData) {
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

        const data = this.aggregateData();

        if (data.length === 0) {
            this.showEmptyState();
            return;
        }

        this.hideEmptyState();

        if (this.state.viewMode === 'table') {
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
