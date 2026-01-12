// Home page logic
class HomeUI {
    constructor() {
        this.token = localStorage.getItem('auth_token');
        this.playerId = localStorage.getItem('player_id');
        this.username = localStorage.getItem('username');
        
        if (!this.token || !this.playerId) {
            window.location.href = 'login.html';
            return;
        }
        
        this.baseUrl = window.location.origin;
        this.initializeElements();
        this.loadPlayerData();
    }
    
    initializeElements() {
        this.playerAvatar = document.getElementById('playerAvatar');
        this.playerName = document.getElementById('playerName');
        this.chipsDisplay = document.getElementById('chipsDisplay');
    }
    
    async loadPlayerData() {
        try {
            const response = await fetch(`${this.baseUrl}/api/v1/players/me`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });
            
            if (response.status === 401) {
                // Token expired or invalid, redirect to login
                console.log('[Home] Token expired, redirecting to login');
                this.logout();
                return;
            }
            
            if (response.ok) {
                const data = await response.json();
                this.updateUI(data);
            } else {
                // If endpoint doesn't exist, use default values
                this.updateUI({
                    username: this.username || 'Player',
                    chips: 1000,
                    avatar: '👤'
                });
            }
        } catch (error) {
            console.error('[Home] Error loading player data:', error);
            // On network errors, still show default values
            this.updateUI({
                username: this.username || 'Player',
                chips: 1000,
                avatar: '👤'
            });
        }
    }
    
    updateUI(data) {
        if (this.playerName) {
            this.playerName.textContent = data.username || this.username || 'Player';
        }
        if (this.chipsDisplay) {
            this.chipsDisplay.textContent = (data.chips || 1000).toLocaleString();
        }
        if (this.playerAvatar) {
            this.playerAvatar.textContent = data.avatar || '👤';
        }
    }
    
    goToTable() {
        // Redirect to table page
        window.location.href = 'table.html';
    }
    
    goToRoulette() {
        window.location.href = 'roulette.html';
    }
    
    logout() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('player_id');
        localStorage.removeItem('username');
        window.location.href = 'login.html';
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.homeUI = new HomeUI();
});
