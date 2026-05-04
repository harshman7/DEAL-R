// Roulette mini-game logic
class RouletteUI {
    constructor() {
        if (redirectToLoginIfUnauthenticated()) {
            return;
        }

        this.token = localStorage.getItem('auth_token');
        this.playerId = localStorage.getItem('player_id');
        this.username = localStorage.getItem('username');

        this.baseUrl = window.location.origin;
        this.isSpinning = false;
        this.initializeElements();
        this.checkAvailability();
    }

    initializeElements() {
        this.rouletteWheel = document.getElementById('rouletteWheel');
        this.rewardDisplay = document.getElementById('rewardDisplay');
        this.dailyStatus = document.getElementById('dailyStatus');
        this.spinBtn = document.getElementById('spinBtn');
    }

    async checkAvailability() {
        try {
            const response = await fetchWithAuth(`${this.baseUrl}/api/v1/players/me`);

            if (response === null) {
                return;
            }

            if (!response.ok) {
                throw new Error('Failed to load player info');
            }

            const data = await response.json();
            const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD format
            const lastRouletteDate = data.last_roulette_date;

            if (lastRouletteDate === today) {
                // Already used today
                this.dailyStatus.textContent = 'You have already spun today. Come back tomorrow!';
                this.dailyStatus.className = 'daily-status used';
                this.spinBtn.disabled = true;
            } else {
                // Available
                this.dailyStatus.textContent = 'Available! Spin the wheel for free chips.';
                this.dailyStatus.className = 'daily-status available';
                this.spinBtn.disabled = false;
            }
        } catch (error) {
            console.error('[Roulette] Error checking availability:', error);
            this.dailyStatus.textContent = 'Error checking availability';
            this.dailyStatus.className = 'daily-status used';
        }
    }

    async spin() {
        if (this.isSpinning) return;

        this.isSpinning = true;
        this.spinBtn.disabled = true;
        this.rewardDisplay.textContent = 'Spinning...';

        // Add spinning animation
        this.rouletteWheel.classList.add('spinning');

        try {
            const response = await fetchWithAuth(`${this.baseUrl}/api/v1/roulette/spin`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            if (response === null) {
                this.rouletteWheel.classList.remove('spinning');
                this.isSpinning = false;
                return;
            }

            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: 'Spin failed' }));
                throw new Error(error.detail || 'Spin failed');
            }

            const data = await response.json();

            // Wait for animation to complete
            setTimeout(() => {
                this.rouletteWheel.classList.remove('spinning');
                this.rewardDisplay.textContent = `+${data.reward}`;
                this.dailyStatus.textContent = `You won ${data.reward} chips! Come back tomorrow.`;
                this.dailyStatus.className = 'daily-status used';
                this.isSpinning = false;

                // Update player chips display if on home page
                if (window.homeUI) {
                    window.homeUI.loadPlayerData();
                }
            }, 4000);
        } catch (error) {
            console.error('[Roulette] Spin error:', error);
            this.rouletteWheel.classList.remove('spinning');
            this.rewardDisplay.textContent = 'Error';
            this.dailyStatus.textContent = error.message || 'Failed to spin';
            this.dailyStatus.className = 'daily-status used';
            this.isSpinning = false;
            this.checkAvailability(); // Re-check in case it was a different error
        }
    }

    logout() {
        clearAuthAndGoLogin();
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.rouletteUI = new RouletteUI();
});
