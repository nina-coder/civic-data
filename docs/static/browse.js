/* browse.js — live filter for the legislator directory */

(function () {
  'use strict';

  var nameInput = document.getElementById('name-search');
  var chamberSelect = document.getElementById('chamber-filter');

  if (!nameInput || !chamberSelect) return;

  var cards = Array.prototype.slice.call(
    document.querySelectorAll('.legislator-card')
  );

  function filterCards() {
    var query = nameInput.value.toLowerCase().trim();
    var chamber = chamberSelect.value.toLowerCase();

    cards.forEach(function (card) {
      var nameMatch = !query || (card.dataset.name || '').indexOf(query) !== -1;
      var chamberMatch = !chamber || (card.dataset.chamber || '') === chamber;
      card.style.display = (nameMatch && chamberMatch) ? '' : 'none';
    });
  }

  nameInput.addEventListener('input', filterCards);
  chamberSelect.addEventListener('change', filterCards);
})();
