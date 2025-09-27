document.addEventListener('DOMContentLoaded', function () {
    const container = document.getElementById('scroll-container');
    if (container) {
        container.addEventListener('wheel', function (e) {
            if (e.deltaY !== 0) {
                e.preventDefault(); // prevent vertical scroll
                container.scrollLeft += e.deltaY; // use Y to scroll X
            }
        });
    }
});