// Clean Game View - Simplified for in-game state
class GameView {
    constructor() {
        this.ws = null;
        this.token = localStorage.getItem('auth_token');
        this.playerId = localStorage.getItem('player_id') || null;
        this.username = localStorage.getItem('username') || null;
        this.tableId = 'table-1';
        this.currentSeat = null;
        this.expectedVersion = 0;
        this.lastState = null;
        
        // URLs
        const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        this.baseUrl = `${protocol}//${host}`;
        this.wsUrl = `${wsProtocol}//${host}`;
        
        // Check if logged in
        if (!this.token || !this.playerId) {
            window.location.href = 'login.html';
            return;
        }
        
        this.initializeElements();
        this.attachEventListeners();
        this.initializeSeats();
        this.updateUserDisplay();
        
        // Auto-connect if table ID is in URL or use default
        const urlParams = new URLSearchParams(window.location.search);
        const tableId = urlParams.get('table') || this.tableId;
        if (tableId) {
            this.tableId = tableId;
            this.connect();
        }
    }

    initializeElements() {
        // Top bar
        this.playerNameEl = document.getElementById('playerName');
        this.tableNameEl = document.getElementById('tableName');
        
        // Status
        this.streetEl = document.getElementById('street');
        this.currentBetEl = document.getElementById('currentBet');
        this.potAmountEl = document.getElementById('potAmount');
        this.potValueEl = document.getElementById('potValue');
        
        // Table
        this.seatsContainer = document.getElementById('seatsContainer');
        this.communityCards = document.getElementById('communityCards');
        this.potDisplay = document.getElementById('potDisplay');
        
        // Your cards
        this.yourCardsSection = document.getElementById('yourCardsSection');
        this.yourCards = document.getElementById('yourCards');
        
        // Actions
        this.actionPanel = document.getElementById('actionPanel');
        this.actionText = document.getElementById('actionText');
        this.actionDetails = document.getElementById('actionDetails');
        this.foldBtn = document.getElementById('foldBtn');
        this.checkBtn = document.getElementById('checkBtn');
        this.callBtn = document.getElementById('callBtn');
        this.betBtn = document.getElementById('betBtn');
        this.raiseBtn = document.getElementById('raiseBtn');
        this.betAmountInput = document.getElementById('betAmount');
    }

    attachEventListeners() {
        this.foldBtn.addEventListener('click', () => this.act('FOLD', 0));
        this.checkBtn.addEventListener('click', () => this.act('CHECK', 0));
        this.callBtn.addEventListener('click', () => this.call());
        this.betBtn.addEventListener('click', () => this.bet());
        this.raiseBtn.addEventListener('click', () => this.raise());
    }

    updateUserDisplay() {
        if (this.playerNameEl) {
            this.playerNameEl.textContent = this.username || this.playerId || 'Player';
        }
        if (this.tableNameEl) {
            this.tableNameEl.textContent = this.tableId;
        }
    }

    initializeSeats() {
        // Create 9 seat elements positioned around the table
        for (let i = 0; i < 9; i++) {
            const seat = document.createElement('div');
            seat.className = 'seat';
            seat.id = `seat-${i}`;
            seat.innerHTML = `
                <div class="seat-name">Seat ${i + 1}</div>
                <div class="seat-stack">-</div>
                <div class="seat-status">Empty</div>
            `;
            this.seatsContainer.appendChild(seat);
        }
    }

    connect() {
        if (this.ws) {
            this.ws.close();
        }

        const wsUrl = `${this.wsUrl}/api/v1/ws/${this.tableId}?token=${this.token}`;
        console.log('[GameView] Connecting to:', wsUrl);
        
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('[GameView] WebSocket connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (e) {
                console.error('[GameView] Error parsing message:', e);
            }
        };

        this.ws.onerror = (error) => {
            console.error('[GameView] WebSocket error:', error);
        };

        this.ws.onclose = () => {
            console.log('[GameView] WebSocket closed');
        };
    }

    handleMessage(data) {
        if (data.type === 'state') {
            this.lastState = data.data;
            this.updateGameState(data.data);
            if (data.version !== undefined) {
                this.expectedVersion = data.version;
            }
        } else if (data.type === 'error') {
            console.error('[GameView] Error:', data.message);
            alert(data.message);
        }
    }

    updateGameState(state) {
        // Update status bar
        this.streetEl.textContent = state.street || 'WAITING';
        this.currentBetEl.textContent = state.current_bet || 0;
        
        // Calculate total pot from all pots
        const totalPot = (state.pots || []).reduce((sum, pot) => sum + (pot.amount || 0), 0);
        this.potAmountEl.textContent = `$${totalPot}`;
        this.potValueEl.textContent = `$${totalPot}`;
        
        // Update seats
        this.updateSeats(state);
        
        // Update community cards
        this.updateCommunityCards(state.community_cards || []);
        
        // Update your cards
        this.updateYourCards(state);
        
        // Update action panel
        this.updateActionPanel(state);
    }

    updateSeats(state) {
        // Ensure we have 9 seats
        const seats = state.seats || [];
        const paddedSeats = [...seats, ...Array(9 - seats.length).fill(null)];
        
        paddedSeats.forEach((seat, index) => {
            const seatEl = document.getElementById(`seat-${index}`);
            if (!seatEl) return;
            
            if (!seat) {
                seatEl.className = 'seat';
                seatEl.innerHTML = `
                    <div class="seat-name">Seat ${index + 1}</div>
                    <div class="seat-stack">-</div>
                    <div class="seat-status">Empty</div>
                `;
                return;
            }
            
            // Determine seat classes
            let classes = 'seat';
            if (seat.status === 'ACTIVE' || seat.status === 'ALL_IN') {
                classes += ' active';
            }
            if (seat.seat_id === state.to_act_seat) {
                classes += ' to-act';
            }
            if (seat.status === 'FOLDED') {
                classes += ' folded';
            }
            if (seat.status === 'ALL_IN') {
                classes += ' all-in';
            }
            
            seatEl.className = classes;
            
            // Player name
            const playerName = seat.player_id || `Player ${index + 1}`;
            const shortName = playerName.length > 10 ? playerName.substring(0, 10) + '...' : playerName;
            
            // Bet info
            const betInfo = seat.committed_total > 0 
                ? `<div class="seat-bet">Bet: ${seat.committed_total}</div>`
                : `<div class="seat-status">${seat.status}</div>`;
            
            seatEl.innerHTML = `
                <div class="seat-name">${shortName}</div>
                <div class="seat-stack">${seat.stack}</div>
                ${betInfo}
            `;
        });
        
        // Update current seat (for action panel)
        this.currentSeat = state.to_act_seat;
    }

    updateCommunityCards(cards) {
        this.communityCards.innerHTML = '';
        
        if (cards.length === 0) {
            return; // No cards to show
        }
        
        cards.forEach(card => {
            const cardEl = this.createCardElement(card);
            this.communityCards.appendChild(cardEl);
        });
    }

    updateYourCards(state) {
        // Find seat with our player_id
        const mySeat = state.seats?.find(s => s && s.player_id === this.playerId);
        
        if (mySeat && mySeat.hole_cards && mySeat.hole_cards.length === 2) {
            // Show cards
            this.yourCardsSection.style.display = 'block';
            this.yourCards.innerHTML = '';
            
            mySeat.hole_cards.forEach(card => {
                const cardEl = this.createCardElement(card);
                this.yourCards.appendChild(cardEl);
            });
            
            console.log('[GameView] ✓ Displayed your cards:', mySeat.hole_cards);
        } else {
            // Hide if no cards
            this.yourCardsSection.style.display = 'none';
            this.yourCards.innerHTML = '';
        }
    }

    createCardElement(card) {
        const cardEl = document.createElement('div');
        cardEl.className = 'card';
        
        // Handle card format: {rank: number, suit: number}
        let rankValue, suitValue;
        
        if (typeof card === 'object' && card !== null) {
            // Handle {rank: 2, suit: 0} format
            if (typeof card.rank === 'number') {
                rankValue = card.rank;
            } else if (card.rank && typeof card.rank === 'object' && 'value' in card.rank) {
                rankValue = card.rank.value;
            } else {
                rankValue = card.rank;
            }
            
            if (typeof card.suit === 'number') {
                suitValue = card.suit;
            } else if (card.suit && typeof card.suit === 'object' && 'value' in card.suit) {
                suitValue = card.suit.value;
            } else {
                suitValue = card.suit;
            }
        } else {
            console.error('[GameView] Invalid card format:', card);
            return cardEl;
        }
        
        // Validate
        if (typeof rankValue !== 'number' || typeof suitValue !== 'number') {
            console.error('[GameView] Card values not numbers:', { rankValue, suitValue, card });
            return cardEl;
        }
        
        const rank = this.getRankSymbol(rankValue);
        const suit = this.getSuitSymbol(suitValue);
        const isRed = suitValue === 1 || suitValue === 2; // Diamonds or Hearts
        
        cardEl.className += isRed ? ' red' : ' black';
        cardEl.innerHTML = `
            <div class="card-rank">${rank}</div>
            <div class="card-suit">${suit}</div>
        `;
        
        return cardEl;
    }

    getRankSymbol(rank) {
        const ranks = {
            2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8', 9: '9', 10: '10',
            11: 'J', 12: 'Q', 13: 'K', 14: 'A'
        };
        return ranks[rank] || rank;
    }

    getSuitSymbol(suit) {
        const suits = { 0: '♣', 1: '♦', 2: '♥', 3: '♠' };
        return suits[suit] || suit;
    }

    updateActionPanel(state) {
        // Find our seat
        const mySeat = state.seats?.find(s => s && s.player_id === this.playerId);
        
        if (!mySeat || mySeat.status === 'FOLDED' || mySeat.status === 'ALL_IN') {
            this.actionPanel.style.display = 'none';
            return;
        }
        
        // Check if it's our turn
        const isMyTurn = state.to_act_seat === mySeat.seat_id;
        
        if (!isMyTurn) {
            this.actionPanel.style.display = 'none';
            return;
        }
        
        // Show action panel
        this.actionPanel.style.display = 'block';
        
        // Calculate call amount
        const callAmount = Math.max(0, (state.current_bet || 0) - (mySeat.committed_street || 0));
        
        // Update action info
        this.actionText.textContent = 'Your turn to act';
        this.actionDetails.textContent = `Stack: ${mySeat.stack} · Bet: ${mySeat.committed_street || 0} · Call: ${callAmount}`;
        
        // Update button states
        this.checkBtn.disabled = callAmount > 0;
        this.callBtn.disabled = callAmount === 0;
        this.callBtn.textContent = callAmount > 0 ? `Call ${callAmount}` : 'Call';
        
        // Set bet amount input
        const minBet = state.min_raise || state.big_blind || 100;
        this.betAmountInput.min = minBet;
        this.betAmountInput.placeholder = `Min: ${minBet}`;
    }

    act(actionType, amount = 0) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.error('[GameView] WebSocket not connected');
            return;
        }
        
        const mySeat = this.lastState?.seats?.find(s => s && s.player_id === this.playerId);
        if (!mySeat) {
            console.error('[GameView] Player not found in seats');
            return;
        }
        
        const command = {
            type: 'act',
            seat_id: mySeat.seat_id,
            action_type: actionType,
            amount: amount,
            idempotency_key: `act-${Date.now()}-${Math.random()}`,
            expected_version: this.expectedVersion
        };
        
        console.log('[GameView] Sending action:', command);
        this.ws.send(JSON.stringify(command));
    }

    call() {
        if (!this.lastState) return;
        
        const mySeat = this.lastState.seats?.find(s => s && s.player_id === this.playerId);
        if (!mySeat) return;
        
        const callAmount = Math.max(0, (this.lastState.current_bet || 0) - (mySeat.committed_street || 0));
        this.act('CALL', callAmount);
    }

    bet() {
        const amount = parseInt(this.betAmountInput.value);
        if (isNaN(amount) || amount <= 0) {
            alert('Please enter a valid bet amount');
            return;
        }
        this.act('BET', amount);
    }

    raise() {
        const amount = parseInt(this.betAmountInput.value);
        if (isNaN(amount) || amount <= 0) {
            alert('Please enter a valid raise amount');
            return;
        }
        this.act('RAISE', amount);
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
    window.pokerUI = new GameView();
});

