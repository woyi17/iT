// AttendTrack — app.js
// Handles: message auto-dismiss, keyboard nav helpers, live clock

document.addEventListener('DOMContentLoaded', function () {

  // Auto-dismiss messages after 5 seconds
  document.querySelectorAll('.message').forEach(function (msg) {
    setTimeout(function () {
      msg.style.transition = 'opacity 0.4s';
      msg.style.opacity = '0';
      setTimeout(function () { msg.remove(); }, 400);
    }, 5000);
  });

  // Keyboard: Enter/Space on buttons that are <a> tags
  document.querySelectorAll('a.btn').forEach(function (el) {
    el.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        el.click();
      }
    });
  });

});
