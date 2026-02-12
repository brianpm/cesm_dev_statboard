/**
 * Case Comparison Tool
 */
class ComparisonTool {
    constructor(app) {
        this.app = app;
        this.compareMode = false;
        this.selectedCases = new Set();
        this.setupEventListeners();
    }

    setupEventListeners() {
        document.getElementById('compareBtn').addEventListener('click', () => {
            this.showComparison();
        });

        document.getElementById('exitCompareMode').addEventListener('click', () => {
            this.toggleCompareMode();
        });
    }

    toggleCompareMode() {
        this.compareMode = !this.compareMode;

        if (this.compareMode) {
            document.getElementById('comparisonControls').style.display = 'block';
            document.getElementById('toggleCompareMode').textContent = 'Exit Compare Mode';
            this.selectedCases.clear();
        } else {
            document.getElementById('comparisonControls').style.display = 'none';
            document.getElementById('toggleCompareMode').textContent = 'Compare Mode';
            this.selectedCases.clear();
        }

        // Re-render table to show/hide checkboxes
        this.app.renderTable();
        this.updateSelectedCount();
    }

    toggleCaseSelection(caseId, selected) {
        if (selected) {
            if (this.selectedCases.size < 4) {
                this.selectedCases.add(caseId);
            } else {
                alert('Maximum 4 cases can be compared at once');
                // Uncheck the checkbox
                const checkbox = document.querySelector(`input[data-case-id="${caseId}"]`);
                if (checkbox) checkbox.checked = false;
            }
        } else {
            this.selectedCases.delete(caseId);
        }

        this.updateSelectedCount();
    }

    updateSelectedCount() {
        const count = this.selectedCases.size;
        document.getElementById('selectedCount').textContent = `${count} case${count !== 1 ? 's' : ''} selected`;

        const compareBtn = document.getElementById('compareBtn');
        compareBtn.disabled = count < 2;
    }

    showComparison() {
        if (this.selectedCases.size < 2) {
            alert('Please select at least 2 cases to compare');
            return;
        }

        const cases = Array.from(this.selectedCases)
            .map(id => this.app.cases.find(c => c.id === id))
            .filter(Boolean);

        this.renderComparison(cases);

        const modal = document.getElementById('comparisonModal');
        modal.style.display = 'block';
    }

    renderComparison(cases) {
        const detailDiv = document.getElementById('comparisonDetail');

        let html = '<h2>Case Comparison</h2>';

        // Configuration table
        html += '<div class="detail-section"><h3>Configuration</h3>';
        html += '<table class="case-table" style="width: 100%"><thead><tr><th>Property</th>';

        cases.forEach(c => {
            html += `<th>${c.case_name.substring(c.case_name.length - 20)}</th>`;
        });

        html += '</tr></thead><tbody>';

        // Add rows for each property
        const properties = [
            { key: 'compset', label: 'Compset' },
            { key: 'resolution', label: 'Resolution' },
            { key: 'experiment_id', label: 'Experiment ID' },
            { key: 'issue_state', label: 'Issue State' },
            { key: 'has_diagnostics', label: 'Has Diagnostics' }
        ];

        properties.forEach(prop => {
            html += `<tr><td><strong>${prop.label}</strong></td>`;
            cases.forEach(c => {
                let value = c[prop.key];
                if (prop.key === 'has_diagnostics') {
                    value = value ? 'Yes' : 'No';
                }
                html += `<td>${value || 'N/A'}</td>`;
            });
            html += '</tr>';
        });

        html += '</tbody></table></div>';

        // Purpose comparison
        html += '<div class="detail-section"><h3>Purpose</h3>';
        html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px;">';

        cases.forEach(c => {
            html += `<div class="stat-item">
                <div class="stat-label">${c.case_name.substring(c.case_name.length - 20)}</div>
                <div style="font-size: 0.9em; margin-top: 8px;">${c.purpose || 'Not specified'}</div>
            </div>`;
        });

        html += '</div></div>';

        // Statistics comparison (if available)
        const casesWithStats = cases.filter(c => c.statistics && Object.keys(c.statistics).length > 0);

        if (casesWithStats.length > 0) {
            html += '<div class="detail-section"><h3>Statistics Summary</h3>';
            html += '<table class="case-table" style="width: 100%"><thead><tr><th>Period</th>';

            cases.forEach(c => {
                html += `<th>${c.case_name.substring(c.case_name.length - 20)}</th>`;
            });

            html += '</tr></thead><tbody>';

            // Get all unique periods
            const periods = new Set();
            cases.forEach(c => {
                if (c.statistics) {
                    Object.keys(c.statistics).forEach(p => periods.add(p));
                }
            });

            Array.from(periods).forEach(period => {
                html += `<tr><td><strong>${period}</strong></td>`;
                cases.forEach(c => {
                    const stats = c.statistics && c.statistics[period];
                    const varCount = stats ? Object.keys(stats).length : 0;
                    html += `<td>${varCount > 0 ? `${varCount} variables` : 'N/A'}</td>`;
                });
                html += '</tr>';
            });

            html += '</tbody></table></div>';
        }

        // Links to GitHub issues
        html += '<div class="detail-section"><h3>GitHub Issues</h3>';
        cases.forEach(c => {
            html += `<p><a href="https://github.com/NCAR/cesm_dev/issues/${c.issue_number}" target="_blank">${c.case_name} (Issue #${c.issue_number})</a></p>`;
        });
        html += '</div>';

        detailDiv.innerHTML = html;
    }
}

// Initialize comparison tool when app is ready
window.addEventListener('DOMContentLoaded', () => {
    const checkApp = setInterval(() => {
        if (window.app) {
            window.comparisonTool = new ComparisonTool(window.app);
            clearInterval(checkApp);
        }
    }, 100);
});
