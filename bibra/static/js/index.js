document.addEventListener('DOMContentLoaded', function() {
  fetch('/v0/')
    .then(response => response.json())
    .then(data => {
      const versionSpan = document.getElementById('version');
      if (versionSpan && data.version) {
        versionSpan.textContent = data.version;
      }
    })
    .catch(err => {
      console.error('Failed to fetch version:', err);
    });
});
