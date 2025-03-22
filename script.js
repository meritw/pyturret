document.addEventListener('DOMContentLoaded', (event) => {
    let isArmed = false;
    const armDisarmButton = document.getElementById('armDisarmButton');

    armDisarmButton.addEventListener('click', () => {
        isArmed = !isArmed;
        armDisarmButton.textContent = isArmed ? 'Disarm' : 'Arm';
        fetch(`/set_armed?armed=${isArmed}`);
    });
});