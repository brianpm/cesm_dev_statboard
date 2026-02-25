/**
 * Namelist Diff Manager
 * Provides side-by-side comparison of component namelist settings across CESM cases.
 * Supports: atmosphere (atm_in), land (lnd_in), sea ice (ice_in), ocean (MOM6).
 */
class NamelistDiffManager {
    constructor(app) {
        this.app = app;
        this.index = {};              // {case_name: {atm: file|null, lnd: ..., ice: ..., ocn: ...}}
        this.cache = {};              // {`${caseName}_${comp}`: parsed_namelist_dict}
        this.selectedCases = new Set();
        this.activeComponent = 'atm';
        this.componentCounts = {};    // {comp: number_of_cases_with_data}
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

        this._computeComponentAvailability();
        this._renderComponentSelector();
        this.renderCaseList();
        this._wireEvents();
    }

    // ─── Component selector ────────────────────────────────────────────────

    _computeComponentAvailability() {
        const comps = ['atm', 'lnd', 'ice', 'ocn'];
        this.componentCounts = {};
        comps.forEach(comp => {
            this.componentCounts[comp] = Object.values(this.index)
                .filter(entry => entry[comp] != null).length;
        });
    }

    _renderComponentSelector() {
        const container = document.getElementById('namelistComponentSelector');
        if (!container) return;

        const labels = { atm: 'Atmosphere', lnd: 'Land', ocn: 'Ocean', ice: 'Sea Ice' };
        container.querySelectorAll('.namelist-comp-btn').forEach(btn => {
            const comp = btn.dataset.component;
            const count = this.componentCounts[comp] || 0;
            if (count === 0) {
                btn.disabled = true;
                btn.classList.add('unavailable');
                btn.title = 'No cases have data for this component';
            } else {
                btn.disabled = false;
                btn.classList.remove('unavailable');
                btn.title = `${count} case${count !== 1 ? 's' : ''} available`;
            }
            btn.classList.toggle('active', comp === this.activeComponent);
            btn.addEventListener('click', () => this._selectComponent(comp));
        });
    }

    _selectComponent(comp) {
        if (this.componentCounts[comp] === 0) return;
        this.activeComponent = comp;
        this.selectedCases.clear();

        // Update button states
        document.querySelectorAll('.namelist-comp-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.component === comp);
        });

        // Hide any existing diff
        const container = document.getElementById('namelistDiffContainer');
        if (container) container.style.display = 'none';

        this.renderCaseList();
        this._updateControls();
    }

    // ─── Case list ─────────────────────────────────────────────────────────

    renderCaseList() {
        const container = document.getElementById('namelistCaseSelector');
        if (!container) return;

        // Filter to cases that have data for the active component
        const names = Object.keys(this.index)
            .filter(n => this.index[n][this.activeComponent] != null)
            .sort();

        if (names.length === 0) {
            container.innerHTML = '<p class="help-text">No cases with namelist data for this component.</p>';
            return;
        }

        const searchId = 'namelistSearch';
        container.innerHTML = `
            <div class="namelist-search-row">
                <input type="text" id="${searchId}" class="namelist-search"
                       placeholder="Filter cases..." />
                <span class="help-text">${names.length} cases with data</span>
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

    // ─── Data fetching ─────────────────────────────────────────────────────

    async fetchNamelist(caseName) {
        const cacheKey = `${caseName}_${this.activeComponent}`;
        if (this.cache[cacheKey]) return this.cache[cacheKey];

        const entry = this.index[caseName];
        if (!entry) return null;
        const filePath = entry[this.activeComponent];
        if (!filePath) return null;

        try {
            const resp = await fetch('data/' + filePath);
            if (!resp.ok) return null;
            const data = await resp.json();
            this.cache[cacheKey] = data;
            return data;
        } catch (e) {
            console.error(`Failed to fetch ${this.activeComponent} namelist for ${caseName}:`, e);
            return null;
        }
    }

    // ─── Diff display ──────────────────────────────────────────────────────

    async showDiff() {
        const selected = Array.from(this.selectedCases);
        if (selected.length < 2) return;

        await Promise.all(selected.map(n => this.fetchNamelist(n)));

        if (this.activeComponent === 'ocn') {
            this._renderOcnDiffTable(selected);
        } else {
            this.renderDiffTable(selected);
        }

        const container = document.getElementById('namelistDiffContainer');
        if (container) container.style.display = '';
    }

    // Standard Fortran namelist diff (atm, lnd, ice)
    renderDiffTable(caseNames) {
        const tableDiv = document.getElementById('namelistDiffTable');
        if (!tableDiv) return;

        const cacheKeys = caseNames.map(n => `${n}_${this.activeComponent}`);

        // Collect all group/key paths across all cases
        const groupKeys = {};   // {group: Set(keys)}
        cacheKeys.forEach(key => {
            const nml = this.cache[key] || {};
            Object.entries(nml).forEach(([group, settings]) => {
                if (!groupKeys[group]) groupKeys[group] = new Set();
                if (settings && typeof settings === 'object') {
                    Object.keys(settings).forEach(k => groupKeys[group].add(k));
                }
            });
        });

        const groups = Object.keys(groupKeys).sort();

        const colWidth = Math.floor(60 / caseNames.length);
        let html = '<table class="namelist-table">';

        html += '<thead><tr><th style="width:20%">Group / Key</th>';
        caseNames.forEach(name => {
            const short = name.length > 40 ? name.substring(0, 38) + '…' : name;
            html += `<th style="width:${colWidth}%" title="${name}">${short}</th>`;
        });
        html += '</tr></thead><tbody>';

        groups.forEach(group => {
            const keys = Array.from(groupKeys[group]).sort();

            html += `<tr class="namelist-group-header">
                <td colspan="${caseNames.length + 1}">&amp;${group}</td>
            </tr>`;

            keys.forEach(key => {
                const values = cacheKeys.map(ck => {
                    const nml = this.cache[ck] || {};
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

    // Ocean diff table: three source sections (MOM_override, MOM_input, input.nml)
    _renderOcnDiffTable(caseNames) {
        const tableDiv = document.getElementById('namelistDiffTable');
        if (!tableDiv) return;

        const cacheKeys = caseNames.map(n => `${n}_ocn`);
        const colWidth = Math.floor(60 / caseNames.length);

        let html = '<table class="namelist-table">';
        html += '<thead><tr><th style="width:20%">Source / Key</th>';
        caseNames.forEach(name => {
            const short = name.length > 40 ? name.substring(0, 38) + '…' : name;
            html += `<th style="width:${colWidth}%" title="${name}">${short}</th>`;
        });
        html += '</tr></thead><tbody>';

        // Determine which sources actually appear in any case
        const hasMOMOverride = cacheKeys.some(ck => {
            const d = this.cache[ck] || {};
            return d.MOM_override && Object.keys(d.MOM_override).length > 0;
        });
        const hasMOMInput = cacheKeys.some(ck => {
            const d = this.cache[ck] || {};
            return d.MOM_input && Object.keys(d.MOM_input).length > 0;
        });
        const hasInputNml = cacheKeys.some(ck => {
            const d = this.cache[ck] || {};
            return d['input.nml'] && Object.keys(d['input.nml']).length > 0;
        });

        // --- MOM_override section ---
        if (hasMOMOverride) {
            const allKeys = new Set();
            cacheKeys.forEach(ck => {
                const over = (this.cache[ck] || {}).MOM_override || {};
                Object.keys(over).forEach(k => allKeys.add(k));
            });
            html += `<tr class="namelist-source-header">
                <td colspan="${caseNames.length + 1}">MOM_override</td>
            </tr>`;
            Array.from(allKeys).sort().forEach(key => {
                html += this._ocnKeyRow(key, cacheKeys, 'MOM_override', false);
            });
        }

        // --- MOM_input section ---
        if (hasMOMInput) {
            // Collect all keys from MOM_input; note which are overridden in any case
            const allKeys = new Set();
            cacheKeys.forEach(ck => {
                const inp = (this.cache[ck] || {}).MOM_input || {};
                Object.keys(inp).forEach(k => allKeys.add(k));
            });
            // Collect all override keys across cases (for strikethrough hint)
            const overrideKeys = new Set();
            cacheKeys.forEach(ck => {
                const over = (this.cache[ck] || {}).MOM_override || {};
                Object.keys(over).forEach(k => overrideKeys.add(k));
            });
            html += `<tr class="namelist-source-header">
                <td colspan="${caseNames.length + 1}">MOM_input</td>
            </tr>`;
            Array.from(allKeys).sort().forEach(key => {
                const isOverridden = overrideKeys.has(key);
                html += this._ocnKeyRow(key, cacheKeys, 'MOM_input', isOverridden);
            });
        }

        // --- input.nml section (standard Fortran namelist groups) ---
        if (hasInputNml) {
            const groupKeys = {};
            cacheKeys.forEach(ck => {
                const nml = (this.cache[ck] || {})['input.nml'] || {};
                Object.entries(nml).forEach(([group, settings]) => {
                    if (!groupKeys[group]) groupKeys[group] = new Set();
                    if (settings && typeof settings === 'object') {
                        Object.keys(settings).forEach(k => groupKeys[group].add(k));
                    }
                });
            });
            html += `<tr class="namelist-source-header">
                <td colspan="${caseNames.length + 1}">input.nml</td>
            </tr>`;
            Object.keys(groupKeys).sort().forEach(group => {
                html += `<tr class="namelist-group-header">
                    <td colspan="${caseNames.length + 1}">&amp;${group}</td>
                </tr>`;
                Array.from(groupKeys[group]).sort().forEach(key => {
                    const values = cacheKeys.map(ck => {
                        const nml = (this.cache[ck] || {})['input.nml'] || {};
                        const grp = nml[group] || {};
                        return grp.hasOwnProperty(key)
                            ? this._formatValue(grp[key])
                            : '<em class="missing-val">—</em>';
                    });
                    const allSame = values.every(v => v === values[0]);
                    html += `<tr class="${allSame ? '' : 'diff-row'}">`;
                    html += `<td class="namelist-key">${key}</td>`;
                    values.forEach((val, i) => {
                        const cellClass = (!allSame && i > 0 && val !== values[0]) ? 'diff-cell' : '';
                        html += `<td class="${cellClass}">${val}</td>`;
                    });
                    html += '</tr>';
                });
            });
        }

        html += '</tbody></table>';
        tableDiv.innerHTML = html;
    }

    // Helper: render one key row for MOM_input or MOM_override sections
    _ocnKeyRow(key, cacheKeys, source, isOverridden) {
        const values = cacheKeys.map(ck => {
            const src = (this.cache[ck] || {})[source] || {};
            return src.hasOwnProperty(key)
                ? this._formatValue(src[key])
                : '<em class="missing-val">—</em>';
        });
        const allSame = values.every(v => v === values[0]);
        const keyClass = isOverridden ? 'namelist-key namelist-overridden' : 'namelist-key';
        const overrideBadge = isOverridden
            ? ' <span class="namelist-override-badge" title="Overridden by MOM_override">↑</span>'
            : '';

        let row = `<tr class="${allSame ? '' : 'diff-row'}">`;
        row += `<td class="${keyClass}">${key}${overrideBadge}</td>`;
        values.forEach((val, i) => {
            const cellClass = (!allSame && i > 0 && val !== values[0]) ? 'diff-cell' : '';
            row += `<td class="${cellClass}">${val}</td>`;
        });
        row += '</tr>';
        return row;
    }

    // ─── Formatting ────────────────────────────────────────────────────────

    _formatValue(val) {
        if (val === null || val === undefined) return '<em class="missing-val">null</em>';
        if (typeof val === 'boolean') return val ? '.true.' : '.false.';
        if (Array.isArray(val)) return val.map(v => this._formatValue(v)).join(', ');
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
