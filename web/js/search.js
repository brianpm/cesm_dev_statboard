/**
 * Search and Filter Manager
 */
class SearchManager {
    constructor(app) {
        this.app = app;
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Search input
        document.getElementById('searchInput').addEventListener('input', (e) => {
            this.applyFilters();
        });

        // Compset filter
        document.getElementById('compsetFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        // Resolution filter
        document.getElementById('resolutionFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        // Diagnostics filter
        document.getElementById('diagnosticsFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        // Clear filters
        document.getElementById('clearFilters').addEventListener('click', () => {
            this.clearFilters();
        });
    }

    applyFilters() {
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();
        const compsetFilter = document.getElementById('compsetFilter').value;
        const resolutionFilter = document.getElementById('resolutionFilter').value;
        const diagnosticsFilter = document.getElementById('diagnosticsFilter').value;

        let filtered = [...this.app.cases];

        // Apply search term
        if (searchTerm) {
            filtered = filtered.filter(caseData => {
                const searchableText = [
                    caseData.case_name,
                    caseData.purpose,
                    caseData.description,
                    caseData.compset,
                    caseData.resolution
                ].filter(Boolean).join(' ').toLowerCase();

                return searchableText.includes(searchTerm);
            });
        }

        // Apply compset filter
        if (compsetFilter) {
            filtered = filtered.filter(c => c.compset === compsetFilter);
        }

        // Apply resolution filter
        if (resolutionFilter) {
            filtered = filtered.filter(c => c.resolution === resolutionFilter);
        }

        // Apply diagnostics filter
        if (diagnosticsFilter) {
            const hasDiagnostics = diagnosticsFilter === 'true';
            filtered = filtered.filter(c => c.has_diagnostics === hasDiagnostics);
        }

        // Update the app with filtered results
        this.app.updateFilteredCases(filtered);
    }

    clearFilters() {
        document.getElementById('searchInput').value = '';
        document.getElementById('compsetFilter').value = '';
        document.getElementById('resolutionFilter').value = '';
        document.getElementById('diagnosticsFilter').value = '';

        this.applyFilters();
    }
}

// Initialize search manager when app is ready
window.addEventListener('DOMContentLoaded', () => {
    // Wait for app to be initialized
    const checkApp = setInterval(() => {
        if (window.app && window.app.cases.length > 0) {
            window.searchManager = new SearchManager(window.app);
            clearInterval(checkApp);
        }
    }, 100);
});
