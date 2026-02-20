/**
 * Namelist Diff Manager
 * Provides side-by-side comparison of atm_in namelist settings across CESM cases.
 */
class NamelistDiffManager {
    constructor(app) {
        this.app = app;
        this.index = {};          // {case_name: {file: 'namelists/...'}}
        this.cache = {};          // {case_name: parsed_namelist_dict}
        this.selectedCases = new Set();
        this.initialized = false;
    }

    async init() {
        if (this.initialized) return;
        this.initialized = true;

        try {
            const resp = await fetch('data/namelists/index.json');
            if (!resp.ok) {
                this._showMessage('No namelist data available. Run export_static.py to generate it.');
                return;
            }
            this.index = await resp.json();
        } catch (e) {
            this._showMessage('Could not load namelist index.');
            return;
        }

        this.renderCaseList();
        this._wireEvents();
    }

    renderCaseList() {
        const container = document.getElementById('namelistCaseSelector');
        if (!container) return;

        const names = Object.keys(this.index).sort();

        if (names.length === 0) {
            container.innerHTML = '<p class="help-text">No cases with namelist data found.</p>';
            return;
        }

        // Search box
        const searchId = 'namelistSearch';
        container.innerHTML = `
            <div class="namelist-search-row">
                <input type="text" id="${searchId}" class="namelist-search"
                       placeholder="Filter cases..." />
                <span class="help-text">${names.length} cases with namelist data</span>
            </div>
            <div class="namelist-case-list" id="namelistCaseList"></div>
        `;

        document.getElementById(searchId).addEventListener('input', (e) => {
            this._filterCaseList(e.target.value.toLowerCase());
        });

        this._renderCaseRows(names);
    }

    _renderCaseRows(names) {
        const list = document.getElementById('namelistCaseList');
        if (!list) return;
        list.innerHTML = '';

        names.forEach(name => {
            // Try to enrich with case info from main app
            const caseInfo = this.app.cases
                ? this.app.cases.find(c => c.case_name === name)
                : null;
            const compset = caseInfo ? (caseInfo.compset || '') : '';
            const issueNum = caseInfo ? (caseInfo.issue_number || '') : '';

            const row = document.createElement('label');
            row.className = 'namelist-case-row';
            row.dataset.caseName = name;

            const checked = this.selectedCases.has(name) ? 'checked' : '';
            row.innerHTML = `
                <input type="checkbox" class="namelist-case-cb" value="${name}" ${checked}>
                <span class="namelist-case-name">${name}</span>
                ${compset ? `<span class="namelist-case-meta">${compset}</span>` : ''}
                ${issueNum ? `<span class="namelist-case-meta">#${issueNum}</span>` : ''}
            `;

            list.appendChild(row);
        });

        // Attach checkbox events
        list.querySelectorAll('.namelist-case-cb').forEach(cb => {
            cb.addEventListener('change', () => this._onCaseToggle(cb));
        });
    }

    _filterCaseList(query) {
        const list = document.getElementById('namelistCaseList');
        if (!list) return;
        list.querySelectorAll('.namelist-case-row').forEach(row => {
            const name = row.dataset.caseName.toLowerCase();
            row.style.display = name.includes(query) ? '' : 'none';
        });
    }

    _onCaseToggle(checkbox) {
        const name = checkbox.value;
        if (checkbox.checked) {
            if (this.selectedCases.size >= 4) {
                checkbox.checked = false;
                alert('You can compare at most 4 cases at once.');
                return;
            }
            this.selectedCases.add(name);
        } else {
            this.selectedCases.delete(name);
        }
        this._updateControls();
    }

    _updateControls() {
        const count = this.selectedCases.size;
        const btn = document.getElementById('namelistDiffBtn');
        const counter = document.getElementById('namelistSelectedCount');
        if (btn) btn.disabled = count < 2;
        if (counter) counter.textContent = `${count} selected`;
    }

    _wireEvents() {
        const btn = document.getElementById('namelistDiffBtn');
        if (btn) {
            btn.addEventListener('click', () => this.showDiff());
        }
    }

    async fetchNamelist(caseName) {
        if (this.cache[caseName]) return this.cache[caseName];
        const entry = this.index[caseName];
        if (!entry) return null;
        try {
            const resp = await fetch('data/' + entry.file);
            if (!resp.ok) return null;
            const data = await resp.json();
            this.cache[caseName] = data;
            return data;
        } catch (e) {
            console.error(`Failed to fetch namelist for ${caseName}:`, e);
            return null;
        }
    }

    async showDiff() {
        const selected = Array.from(this.selectedCases);
        if (selected.length < 2) return;

        // Fetch all selected namelists in parallel
        await Promise.all(selected.map(n => this.fetchNamelist(n)));

        this.renderDiffTable(selected);

        const container = document.getElementById('namelistDiffContainer');
        if (container) container.style.display = '';
    }

    renderDiffTable(caseNames) {
        const tableDiv = document.getElementById('namelistDiffTable');
        if (!tableDiv) return;

        // Collect all group/key paths across all cases
        const groupKeys = {};   // {group: Set(keys)}
        caseNames.forEach(name => {
            const nml = this.cache[name] || {};
            Object.entries(nml).forEach(([group, settings]) => {
                if (!groupKeys[group]) groupKeys[group] = new Set();
                if (settings && typeof settings === 'object') {
                    Object.keys(settings).forEach(k => groupKeys[group].add(k));
                }
            });
        });

        const groups = Object.keys(groupKeys).sort();

        // Build table HTML
        const colWidth = Math.floor(60 / caseNames.length);
        let html = '<table class="namelist-table">';

        // Header row
        html += '<thead><tr><th style="width:20%">Group / Key</th>';
        caseNames.forEach(name => {
            const short = name.length > 40 ? name.substring(0, 38) + '…' : name;
            html += `<th style="width:${colWidth}%" title="${name}">${short}</th>`;
        });
        html += '</tr></thead><tbody>';

        groups.forEach(group => {
            const keys = Array.from(groupKeys[group]).sort();

            // Group header row
            html += `<tr class="namelist-group-header">
                <td colspan="${caseNames.length + 1}">&amp;${group}</td>
            </tr>`;

            keys.forEach(key => {
                const values = caseNames.map(name => {
                    const nml = this.cache[name] || {};
                    const grp = nml[group] || {};
                    return grp.hasOwnProperty(key)
                        ? this._formatValue(grp[key])
                        : '<em class="missing-val">—</em>';
                });

                const allSame = values.every(v => v === values[0]);
                const rowClass = allSame ? '' : 'diff-row';

                html += `<tr class="${rowClass}">`;
                html += `<td class="namelist-key">${key}</td>`;
                values.forEach((val, i) => {
                    const cellClass = (!allSame && i > 0 && val !== values[0]) ? 'diff-cell' : '';
                    html += `<td class="${cellClass}">${val}</td>`;
                });
                html += '</tr>';
            });
        });

        html += '</tbody></table>';
        tableDiv.innerHTML = html;
    }

    _formatValue(val) {
        if (val === null || val === undefined) return '<em class="missing-val">null</em>';
        if (typeof val === 'boolean') return val ? '.true.' : '.false.';
        if (Array.isArray(val)) return val.map(v => this._formatValue(v)).join(', ');
        // Escape HTML special chars for strings
        return String(val)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    _showMessage(msg) {
        const container = document.getElementById('namelistCaseSelector');
        if (container) container.innerHTML = `<p class="help-text">${msg}</p>`;
    }
}
