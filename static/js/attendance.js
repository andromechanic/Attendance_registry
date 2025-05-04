document.addEventListener('DOMContentLoaded', function() {
    const selectAll = document.getElementById('select-all');
    if (!selectAll) return;
  
    selectAll.addEventListener('change', function() {
      // toggle all checkboxes in the table body
      const checkboxes = document.querySelectorAll('.attendance-card tbody input[type="checkbox"]');
      checkboxes.forEach(cb => cb.checked = selectAll.checked);
    });
  });
  