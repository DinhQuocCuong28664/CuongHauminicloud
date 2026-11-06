// Nạp đồng bộ trong <head> để lựa chọn sáng/tối đã lưu áp dụng trước lần vẽ đầu tiên (không chớp).
(function () {
  try {
    var saved = localStorage.getItem('mmc-theme');
    if (saved === 'light' || saved === 'dark') document.documentElement.dataset.theme = saved;
  } catch (e) { /* bị chặn lưu trữ: theo cài đặt của hệ điều hành */ }
})();
