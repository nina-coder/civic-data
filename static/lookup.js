/* lookup.js — address-to-district lookup using GeoJSON + Turf.js */

(function () {
  'use strict';

  var form = document.getElementById('lookup-form');
  var errorDiv = document.getElementById('lookup-error');
  var loadingDiv = document.getElementById('lookup-loading');
  var resultsDiv = document.getElementById('lookup-results');
  var cardsDiv = document.getElementById('results-cards');

  if (!form) return;

  // --- Geocoding via the US Census Geocoder (free, no key required) ---
  function geocodeAddress(address) {
    var url = 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress'
      + '?address=' + encodeURIComponent(address)
      + '&benchmark=Public_AR_Current&format=json';

    return fetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error('Geocoder request failed.');
        return res.json();
      })
      .then(function (data) {
        var matches = data
          && data.result
          && data.result.addressMatches;
        if (!matches || matches.length === 0) {
          throw new Error('Address not found. Please check the address and try again.');
        }
        var coords = matches[0].coordinates;
        return { lng: coords.x, lat: coords.y };
      });
  }

  // --- Load a GeoJSON file ---
  function loadGeoJSON(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error('Could not load district boundaries.');
      return res.json();
    });
  }

  // --- Find which feature (if any) contains the point ---
  function findDistrict(geojson, lng, lat) {
    var pt = turf.point([lng, lat]);
    for (var i = 0; i < geojson.features.length; i++) {
      var feature = geojson.features[i];
      try {
        if (turf.booleanPointInPolygon(pt, feature)) {
          return feature.properties;
        }
      } catch (e) {
        // skip invalid geometries
      }
    }
    return null;
  }

  // --- Build a result card using safe DOM methods ---
  function buildCard(label, props) {
    var article = document.createElement('article');

    var title = document.createElement('h3');
    title.textContent = label;
    article.appendChild(title);

    if (props) {
      Object.keys(props).forEach(function (key) {
        var p = document.createElement('p');
        p.style.margin = '0.25rem 0';
        var strong = document.createElement('strong');
        strong.textContent = key + ': ';
        p.appendChild(strong);
        p.appendChild(document.createTextNode(String(props[key])));
        article.appendChild(p);
      });
    } else {
      var p = document.createElement('p');
      p.textContent = 'No district found for this address.';
      article.appendChild(p);
    }

    return article;
  }

  function showError(msg) {
    errorDiv.textContent = msg;
    errorDiv.removeAttribute('hidden');
  }

  function clearUI() {
    errorDiv.setAttribute('hidden', '');
    errorDiv.textContent = '';
    loadingDiv.setAttribute('hidden', '');
    resultsDiv.setAttribute('hidden', '');
    // Clear previous cards safely
    while (cardsDiv.firstChild) {
      cardsDiv.removeChild(cardsDiv.firstChild);
    }
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();

    var addressInput = document.getElementById('address-input');
    var address = addressInput ? addressInput.value.trim() : '';
    if (!address) return;

    clearUI();
    loadingDiv.removeAttribute('hidden');

    geocodeAddress(address)
      .then(function (coords) {
        return Promise.all([
          loadGeoJSON('data/senate_districts.geojson'),
          loadGeoJSON('data/house_districts.geojson'),
          Promise.resolve(coords),
        ]);
      })
      .then(function (results) {
        var senateGeo = results[0];
        var houseGeo = results[1];
        var coords = results[2];

        loadingDiv.setAttribute('hidden', '');

        var senateProps = findDistrict(senateGeo, coords.lng, coords.lat);
        var houseProps = findDistrict(houseGeo, coords.lng, coords.lat);

        cardsDiv.appendChild(buildCard('State Senate', senateProps));
        cardsDiv.appendChild(buildCard('State House', houseProps));

        resultsDiv.removeAttribute('hidden');
      })
      .catch(function (err) {
        loadingDiv.setAttribute('hidden', '');
        showError(err.message || 'An error occurred. Please try again.');
      });
  });
})();
