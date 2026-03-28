/* lookup.js — address-to-district lookup using GeoJSON + Turf.js */

(function () {
  'use strict';

  var form = document.getElementById('lookup-form');
  var errorDiv = document.getElementById('lookup-error');
  var loadingDiv = document.getElementById('lookup-loading');
  var resultsDiv = document.getElementById('lookup-results');
  var cardsDiv = document.getElementById('results-cards');

  if (!form) return;

  // --- JSONP geocoding (Census Geocoder doesn't support CORS) ---
  var _jsonpCounter = 0;
  function geocodeAddress(address) {
    return new Promise(function (resolve, reject) {
      var callbackName = '_censusGeocodeCallback' + (_jsonpCounter++);
      var timeout = setTimeout(function () {
        cleanup();
        reject(new Error('Address lookup timed out. Please try again.'));
      }, 10000);

      function cleanup() {
        clearTimeout(timeout);
        delete window[callbackName];
        var script = document.getElementById(callbackName);
        if (script) script.parentNode.removeChild(script);
      }

      window[callbackName] = function (data) {
        cleanup();
        var matches = data && data.result && data.result.addressMatches;
        if (!matches || matches.length === 0) {
          reject(new Error("We couldn't find that address. Try including the city and state (e.g., '123 Main St, Denver, CO 80203')."));
          return;
        }
        var match = matches[0];
        var state = match.addressComponents && match.addressComponents.state;
        if (state && state !== 'CO') {
          reject(new Error('This tool covers Colorado. The address you entered appears to be in ' + state + '.'));
          return;
        }
        resolve({ lng: match.coordinates.x, lat: match.coordinates.y });
      };

      var script = document.createElement('script');
      script.id = callbackName;
      script.src = 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress'
        + '?address=' + encodeURIComponent(address)
        + '&benchmark=Public_AR_Current&format=jsonp&callback=' + callbackName;
      document.head.appendChild(script);
    });
  }

  // --- Load JSON/GeoJSON files ---
  function loadJSON(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error('Could not load ' + url);
      return res.json();
    });
  }

  // --- Find which district polygon contains the point ---
  function findDistrictNumber(geojson, lng, lat, propKey) {
    var pt = turf.point([lng, lat]);
    for (var i = 0; i < geojson.features.length; i++) {
      var feature = geojson.features[i];
      try {
        if (turf.booleanPointInPolygon(pt, feature)) {
          var raw = feature.properties[propKey] || feature.properties.NAME || '';
          return parseInt(raw, 10);
        }
      } catch (e) {
        // skip invalid geometries
      }
    }
    return null;
  }

  // --- Find legislator by chamber and district ---
  function findLegislator(legislators, chamber, district) {
    for (var i = 0; i < legislators.length; i++) {
      if (legislators[i].chamber === chamber && legislators[i].district === district) {
        return legislators[i];
      }
    }
    return null;
  }

  // --- Build a legislator card using safe DOM methods ---
  function buildLegislatorCard(leg, chamberLabel) {
    var article = document.createElement('article');
    article.className = 'legislator-card';

    // Header with photo
    var header = document.createElement('header');
    if (leg.photo_url) {
      var img = document.createElement('img');
      img.src = leg.photo_url;
      img.alt = 'Photo of ' + leg.name;
      img.className = 'legislator-photo';
      header.appendChild(img);
    } else {
      var placeholder = document.createElement('div');
      placeholder.className = 'legislator-photo placeholder';
      placeholder.textContent = (leg.given_name || '?').charAt(0) + (leg.family_name || '').charAt(0);
      header.appendChild(placeholder);
    }
    article.appendChild(header);

    // Name as link to detail page
    var h3 = document.createElement('h3');
    var link = document.createElement('a');
    var slug = leg.id.split('/').pop();
    link.href = 'legislators/' + slug + '.html';
    link.textContent = leg.name;
    h3.appendChild(link);
    article.appendChild(h3);

    // Party badge + district
    var info = document.createElement('p');
    var badge = document.createElement('span');
    badge.className = 'party-badge ' + (leg.party || '').toLowerCase();
    badge.textContent = (leg.party || '?').charAt(0);
    info.appendChild(badge);
    info.appendChild(document.createTextNode(' ' + chamberLabel + ' District ' + leg.district));
    article.appendChild(info);

    // Email if available
    if (leg.email) {
      var emailP = document.createElement('p');
      var emailLink = document.createElement('a');
      emailLink.href = 'mailto:' + leg.email;
      emailLink.textContent = leg.email;
      emailP.appendChild(emailLink);
      article.appendChild(emailP);
    }

    // Website link
    if (leg.website) {
      var siteP = document.createElement('p');
      var siteLink = document.createElement('a');
      siteLink.href = leg.website;
      siteLink.textContent = 'Official Page';
      siteLink.target = '_blank';
      siteLink.rel = 'noopener';
      siteP.appendChild(siteLink);
      article.appendChild(siteP);
    }

    return article;
  }

  // --- Build a "not found" card ---
  function buildNotFoundCard(chamberLabel) {
    var article = document.createElement('article');
    var h3 = document.createElement('h3');
    h3.textContent = chamberLabel;
    article.appendChild(h3);
    var p = document.createElement('p');
    p.textContent = 'No matching legislator found for this district.';
    article.appendChild(p);
    return article;
  }

  // --- UI helpers ---
  function showError(msg) {
    errorDiv.textContent = msg;
    errorDiv.removeAttribute('hidden');
  }

  function clearUI() {
    errorDiv.setAttribute('hidden', '');
    errorDiv.textContent = '';
    loadingDiv.setAttribute('hidden', '');
    resultsDiv.setAttribute('hidden', '');
    while (cardsDiv.firstChild) {
      cardsDiv.removeChild(cardsDiv.firstChild);
    }
  }

  // --- Form submission ---
  form.addEventListener('submit', function (e) {
    e.preventDefault();

    var addressInput = document.getElementById('address-input');
    var address = addressInput ? addressInput.value.trim() : '';
    if (!address) return;

    clearUI();
    loadingDiv.removeAttribute('hidden');

    // Load all data in parallel, then geocode
    Promise.all([
      loadJSON('data/senate.geojson'),
      loadJSON('data/house.geojson'),
      loadJSON('data/legislators.json'),
      geocodeAddress(address),
    ])
      .then(function (results) {
        var senateGeo = results[0];
        var houseGeo = results[1];
        var legislators = results[2];
        var coords = results[3];

        loadingDiv.setAttribute('hidden', '');

        // Find district numbers
        var senateDistrict = findDistrictNumber(senateGeo, coords.lng, coords.lat, 'SLDUST');
        var houseDistrict = findDistrictNumber(houseGeo, coords.lng, coords.lat, 'SLDLST');

        // Find legislators
        var senator = senateDistrict ? findLegislator(legislators, 'senate', senateDistrict) : null;
        var rep = houseDistrict ? findLegislator(legislators, 'house', houseDistrict) : null;

        if (!senator && !rep) {
          showError("We found your address but couldn't match it to a legislative district. This may be a boundary data issue.");
          return;
        }

        if (senator) {
          cardsDiv.appendChild(buildLegislatorCard(senator, 'Senate'));
        } else {
          cardsDiv.appendChild(buildNotFoundCard('State Senate'));
        }

        if (rep) {
          cardsDiv.appendChild(buildLegislatorCard(rep, 'House'));
        } else {
          cardsDiv.appendChild(buildNotFoundCard('State House'));
        }

        resultsDiv.removeAttribute('hidden');
      })
      .catch(function (err) {
        loadingDiv.setAttribute('hidden', '');
        showError(err.message || 'An error occurred. Please try again.');
      });
  });
})();
