let globalForms = [], currentStructure = [];

async function init() {
    try {
        const res = await fetch('/api/forms?active_only=true');
        globalForms = await res.json();
        const sel = document.getElementById('formSelect');
        sel.innerHTML = '<option value="" disabled selected>Select Event/Course...</option>';
        if (globalForms.length === 0) sel.innerHTML = '<option disabled>No active forms found.</option>';
        globalForms.forEach((f, i) => { const o = document.createElement('option'); o.value = i; o.text = `${f.course_name} : ${f.title}`; sel.appendChild(o); });
    } catch (e) { console.error("Error:", e); }
}

function renderForm() {
    const sel = document.getElementById('formSelect');
    if (!sel.value) return; 
    const form = globalForms[sel.value];
    currentStructure = form.structure;
    document.getElementById('selectorCard').classList.add('hidden');
    document.getElementById('formCard').classList.remove('hidden');
    document.getElementById('dynamicTitle').innerText = `${form.title} - ${form.course_name}`;
    const con = document.getElementById('questionsArea'); con.innerHTML = '';
    
    currentStructure.forEach((q, i) => {
        let inp = '';
        const isRequired = q.required !== false;
        if (q.type === 'text') {
            inp = `<input type="text" name="q_${i}" class="w-full p-4 bg-white border border-slate-200 rounded-xl outline-none focus:border-blue-500 transition" ${isRequired ? 'required' : ''} placeholder="Comment...">`;
        }
        else if (q.type === 'rating_5') {
            inp = `<div class="flex gap-4 justify-center bg-slate-50 p-4 rounded-xl border border-slate-200">` + [1,2,3,4,5].map(s => `<label class="cursor-pointer hover:scale-110 transition flex flex-col items-center gap-1"><input type="radio" name="q_${i}" value="${s}" ${isRequired ? 'required' : ''} class="hidden peer"><span class="w-10 h-10 flex items-center justify-center rounded-full bg-white border border-slate-200 text-lg font-bold text-slate-400 peer-checked:bg-blue-600 peer-checked:text-white peer-checked:border-blue-600 peer-checked:scale-110 transition shadow-sm">${s}</span></label>`).join('') + `</div>`;
        }
        else if (q.type === 'rating_3') {
            // Renders only 1, 2, 3 as requested by mentor
            inp = `<div class="flex gap-6 justify-center bg-slate-50 p-4 rounded-xl border border-slate-200">` + [1,2,3].map(s => `<label class="cursor-pointer hover:scale-110 transition flex flex-col items-center gap-1"><input type="radio" name="q_${i}" value="${s}" ${isRequired ? 'required' : ''} class="hidden peer"><span class="w-12 h-12 flex items-center justify-center rounded-full bg-white border border-slate-200 text-xl font-bold text-slate-400 peer-checked:bg-blue-600 peer-checked:text-white peer-checked:border-blue-600 peer-checked:scale-110 transition shadow-sm">${s}</span></label>`).join('') + `</div>`;
        }
        con.innerHTML += `<div><label class="block text-sm font-bold text-slate-700 mb-2">${q.text} <span class="text-xs font-normal text-slate-400">${isRequired ? '(Mandatory)' : '(Optional)'}</span></label>${inp}</div>`;
    });
}

document.getElementById('dynamicForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = globalForms[document.getElementById('formSelect').value];
    const answers = currentStructure.map((q, i) => {
        let val = '';
        if (q.type.startsWith('rating')) { const el = document.querySelector(`input[name="q_${i}"]:checked`); val = el ? el.value : ''; }
        else val = document.querySelector(`[name="q_${i}"]`).value;
        return { question: q.text, answer: val, type: q.type, mappings: q.mappings || [] };
    });
    
    const payload = {
        form_id: form.id,
        form_title: form.title,
        student_name: document.getElementById('student_name').value || 'Anonymous',
        answers
    };
    
    try {
        const res = await fetch('/api/submit_feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        const data = await res.json();
        if (!res.ok) {
            return alert(data.message || data.error || 'Submission failed');
        }
        document.getElementById('resultModal').classList.remove('hidden');
    } catch(e) { alert("Error submitting"); }
});

init();