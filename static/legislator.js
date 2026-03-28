/* legislator.js — bill subject filter on legislator detail pages */

(function () {
  'use strict';

  var billSearch = document.getElementById('bill-search');
  var billsTable = document.getElementById('bills-table');

  if (!billSearch || !billsTable) return;

  var tbody = billsTable.querySelector('tbody');
  if (!tbody) return;

  var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));

  function filterBills() {
    var query = billSearch.value.toLowerCase().trim();

    rows.forEach(function (row) {
      if (!query) {
        row.style.display = '';
        return;
      }

      var subjects = (row.dataset.subjects || '').toLowerCase();
      var titleCell = row.cells[2] ? row.cells[2].textContent.toLowerCase() : '';
      var match = subjects.indexOf(query) !== -1 || titleCell.indexOf(query) !== -1;
      row.style.display = match ? '' : 'none';
    });
  }

  billSearch.addEventListener('input', filterBills);
})();
