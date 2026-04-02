let globalForms = [];
let currentForm = null;
let currentStructure = [];

function escapeHtml(text) {
    return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function getTokenFromUrl() {
    const fromHidden = (document.getElementById('publishedToken')?.value || '').trim();
    if (fromHidden) {
        return fromHidden;
    }
    const params = new URLSearchParams(window.location.search);
    return (params.get('token') || '').trim();
}

function setNotice(type, message) {
    const box = document.getElementById('formNotice');
    if (!box) {
        return;
    }
    if (!message) {
        box.className = 'notice hidden';
        box.textContent = '';
        return;
    }
    box.textContent = message;
    box.className = `notice ${type === 'error' ? 'notice-error' : 'notice-info'}`;
}

function getAnswerValue(index, type) {
    if (type.startsWith('rating')) {
        const checked = document.querySelector(`input[name="q_${index}"]:checked`);
        return checked ? checked.value : '';
    }
    const el = document.querySelector(`[name="q_${index}"]`);
    return el ? String(el.value || '').trim() : '';
}

function updateProgress() {
    const requiredIndexes = currentStructure
        .map((q, i) => ({ q, i }))
        .filter(({ q }) => q.required !== false)
        .map(({ i }) => i);

    let answeredRequired = 0;
    requiredIndexes.forEach((idx) => {
        const val = getAnswerValue(idx, currentStructure[idx].type);
        if (val !== '') {
            answeredRequired += 1;
        }
    });

    const totalRequired = requiredIndexes.length;
    const pct = totalRequired === 0 ? 100 : Math.round((answeredRequired / totalRequired) * 100);
    document.getElementById('progressMeta').textContent = `${answeredRequired} / ${totalRequired} required answered`;
    document.getElementById('progressFill').style.width = `${pct}%`;
}

function questionHtml(question, index) {
    const safeText = escapeHtml(question.text || `Question ${index + 1}`);
    const isRequired = question.required !== false;
    const requiredToken = isRequired ? '<span class="required-star">*</span>' : '<span class="question-optional">(Optional)</span>';

    let inputHtml = '';
    if (question.type === 'text') {
        inputHtml = `<textarea name="q_${index}" class="field-textarea" placeholder="Write your feedback"></textarea>`;
    } else {
        const values = question.type === 'rating_3' ? [1, 2, 3] : [1, 2, 3, 4, 5];
        inputHtml = `<div class="rating-grid">${values.map((v) => `<label class="rating-option"><input type="radio" name="q_${index}" value="${v}"><span class="rating-pill">${v}</span></label>`).join('')}</div>`;
    }

    return `<div class="question-card" data-question-index="${index}"><label class="question-label">${safeText} ${requiredToken}</label>${inputHtml}</div>`;
}

function bindProgressListeners() {
    const form = document.getElementById('dynamicForm');
    form.querySelectorAll('input, textarea, select').forEach((el) => {
        el.addEventListener('change', updateProgress);
        el.addEventListener('input', updateProgress);
    });
}

function renderSelectedForm(form) {
    currentForm = form;
    currentStructure = form.structure || [];

    document.getElementById('selectorCard').classList.add('hidden');
    document.getElementById('formCard').classList.remove('hidden');
    document.getElementById('dynamicTitle').textContent = `${form.title} - ${form.course_name}`;

    const con = document.getElementById('questionsArea');
    con.innerHTML = currentStructure.map((q, i) => questionHtml(q, i)).join('');
    setNotice(null, '');
    bindProgressListeners();
    updateProgress();
}

async function init() {
    try {
        const directToken = getTokenFromUrl();
        if (directToken) {
            const directRes = await fetch(`/api/forms/published/${encodeURIComponent(directToken)}`);
            const directData = await directRes.json();
            if (!directRes.ok) {
                setNotice('error', directData.error || 'This form is not available.');
                return;
            }
            globalForms = [directData];
            renderSelectedForm(directData);
            return;
        }

        const res = await fetch('/api/forms?active_only=true');
        globalForms = await res.json();
        const sel = document.getElementById('formSelect');
        sel.innerHTML = '<option value="" disabled selected>Select Event/Course...</option>';
        if (globalForms.length === 0) {
            sel.innerHTML = '<option disabled>No active forms found.</option>';
            return;
        }
        globalForms.forEach((f, i) => {
            const o = document.createElement('option');
            o.value = i;
            o.text = `${f.course_name} : ${f.title}`;
            sel.appendChild(o);
        });
    } catch (e) {
        console.error('Error:', e);
    }
}

function renderForm() {
    const sel = document.getElementById('formSelect');
    if (!sel.value) {
        return;
    }
    const selected = globalForms[Number(sel.value)];
    if (!selected) {
        return;
    }
    renderSelectedForm(selected);
}

async function handleSubmit(event) {
    event.preventDefault();
    if (!currentForm) {
        return;
    }

    setNotice(null, '');
    const requiredMissing = [];
    const answers = currentStructure.map((q, i) => {
        const value = getAnswerValue(i, q.type);
        if (q.required !== false && value === '') {
            requiredMissing.push(i);
        }
        return {
            question: q.text,
            answer: value,
            type: q.type,
            mappings: q.mappings || []
        };
    });

    if (requiredMissing.length > 0) {
        setNotice('error', 'Please complete all required questions before submitting.');
        const firstMissing = document.querySelector(`[data-question-index="${requiredMissing[0]}"]`);
        if (firstMissing) {
            firstMissing.classList.add('shake');
            firstMissing.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => firstMissing.classList.remove('shake'), 700);
        }
        return;
    }

    const submitBtn = document.getElementById('submitBtn');
    const submitText = document.getElementById('submitBtnText');
    submitBtn.disabled = true;
    submitText.textContent = 'Submitting...';

    const payload = {
        form_id: currentForm.id,
        form_title: currentForm.title,
        student_name: (document.getElementById('student_name').value || 'Anonymous').trim() || 'Anonymous',
        answers
    };

    try {
        const res = await fetch('/api/submit_feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
            setNotice('error', data.message || data.error || 'Submission failed.');
            return;
        }
        document.getElementById('resultModal').classList.remove('hidden');
        document.getElementById('resultModal').classList.add('flex');
    } catch (e) {
        setNotice('error', 'Unable to submit right now. Please retry.');
    } finally {
        submitBtn.disabled = false;
        submitText.textContent = 'Submit Feedback';
    }
}

document.getElementById('dynamicForm').addEventListener('submit', handleSubmit);
window.renderForm = renderForm;

init();