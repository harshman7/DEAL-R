// Poker Engine Web UI
class PokerUI {
    constructor() {
        this.ws = null;
        this.token = localStorage.getItem('auth_token');
        this.playerId = localStorage.getItem('player_id') || null;
        this.username = localStorage.getItem('username') || null;
        this.tableId = null; // Will be set when finding/creating table
        this.playerChips = 1000; // Default, will be loaded from API
        this.currentSeat = null;
        this.expectedVersion = 0;
        const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        this.baseUrl = `${protocol}//${host}`;
        this.wsUrl = `${wsProtocol}//${host}`;
        
        if (!this.token || !this.playerId) {
            window.location.href = 'login.html';
            return;
        }
        
        this.initializeElements();
        this.attachEventListeners();
        this.updateUserDisplay();
        this.loadPlayerChips();
    }

    initializeElements() {
        this.tableNameEl = document.getElementById('tableName');
        this.playersRow = document.getElementById('playersRow');
        this.communityCards = document.getElementById('communityCards');
        this.potDisplay = document.getElementById('potDisplay');
        this.potValueEl = document.getElementById('potValue');
        this.actionCenter = document.getElementById('actionCenter');
        this.waitBtn = document.getElementById('waitBtn');
        this.startHandBtn = document.getElementById('startHandBtn');
        this.actionPanel = document.getElementById('actionPanel');
        this.foldBtn = document.getElementById('foldBtn');
        this.checkBtn = document.getElementById('checkBtn');
        this.callBtn = document.getElementById('callBtn');
        this.betBtn = document.getElementById('betBtn');
        this.raiseBtn = document.getElementById('raiseBtn');
        this.betAmountInput = document.getElementById('betAmount');
        this.actionInfo = document.getElementById('actionInfo');
        this.yourCards = document.getElementById('yourCards');
        this.playerAvatar = document.getElementById('playerAvatar');
        this.playerStack = document.getElementById('playerStack');
        this.debugPanel = document.getElementById('debugPanel');
        this.debugContent = document.getElementById('debugContent');
        this.debugEnabled = false;
        this.lastState = null;
    }
    
    toggleDebug() {
        this.debugEnabled = !this.debugEnabled;
        if (this.debugPanel) {
            this.debugPanel.style.display = this.debugEnabled ? 'block' : 'none';
        }
    }
    
    debugState(state) {
        if (!this.debugEnabled || !this.debugContent) return;
        const mySeat = state.seats?.find(s => s?.player_id === this.playerId);
        const myCards = mySeat?.hole_cards || null;
        const allSeats = state.seats?.map((s, idx) => ({
            seat: idx,
            player_id: s?.player_id,
            has_cards: !!s?.hole_cards,
            cards: s?.hole_cards
        })) || [];
        this.debugContent.innerHTML = `
            <div style="margin-bottom: 8px;"><strong>My Player ID:</strong> ${this.playerId || 'null'}</div>
            <div style="margin-bottom: 8px;"><strong>My Seat:</strong> ${mySeat ? `Seat ${mySeat.seat_id} (${mySeat.player_id})` : 'Not seated'}</div>
            <div style="margin-bottom: 8px;"><strong>My Cards:</strong> ${myCards ? JSON.stringify(myCards, null, 2) : 'None'}</div>
            <div style="margin-bottom: 8px;"><strong>All Seats:</strong></div>
            <pre style="font-size: 10px; overflow: auto; max-height: 150px;">${JSON.stringify(allSeats, null, 2)}</pre>
            <div style="margin-top: 8px; font-size: 9px; color: #aaa;">Raw State:</div>
            <pre style="font-size: 9px; overflow: auto; max-height: 100px; color: #aaa;">${JSON.stringify(state, null, 2).substring(0, 500)}...</pre>
        `;
    }

    attachEventListeners() {
        if (this.foldBtn) this.foldBtn.addEventListener('click', () => this.act('FOLD', 0));
        if (this.checkBtn) this.checkBtn.addEventListener('click', () => this.act('CHECK', 0));
        if (this.callBtn) this.callBtn.addEventListener('click', () => this.call());
        if (this.betBtn) this.betBtn.addEventListener('click', () => this.bet());
        if (this.raiseBtn) this.raiseBtn.addEventListener('click', () => this.raise());
        
        // Start hand button is already attached via onclick in HTML
        this.connect();
    }

    updateUserDisplay() {
        if (this.tableNameEl) {
            this.tableNameEl.textContent = this.tableId;
        }
        if (this.playerAvatar) {
            this.playerAvatar.textContent = this.getAvatarEmoji(this.username || this.playerId);
        }
    }
    
    getAvatarEmoji(name) {
        if (!name) return '👤';
        const avatars = ['👤', '😊', '😎', '🤓', '😄', '🙂', '😃', '😁'];
        let hash = 0;
        for (let i = 0; i < name.length; i++) {
            hash = name.charCodeAt(i) + ((hash << 5) - hash);
        }
        return avatars[Math.abs(hash) % avatars.length];
    }

    logout() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('player_id');
        localStorage.removeItem('username');
        window.location.href = 'login.html';
    }

    async connect() {
        if (!this.token || !this.playerId) {
            window.location.href = 'login.html';
            return;
        }
        
        try {
            // Find or create a table (max 6 players)
            const response = await fetch(`${this.baseUrl}/api/v1/tables/find-or-create`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });
            
            if (!response.ok) {
                throw new Error('Failed to find or create table');
            }
            
            const data = await response.json();
            this.tableId = data.table_id;
            
            if (this.tableNameEl) {
                this.tableNameEl.textContent = this.tableId;
            }
            
            console.log(`[UI] ${data.action} table: ${this.tableId}`);
            
            // Connect to WebSocket
            const tokenParam = this.token ? `?token=${encodeURIComponent(this.token)}` : '';
            const wsUrl = `${this.wsUrl}/ws/tables/${this.tableId}${tokenParam}`;
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('[UI] WebSocket connected');
            };
            this.ws.onmessage = (event) => {
                try {
                    this.handleMessage(JSON.parse(event.data));
                } catch (e) {
                    console.error('[UI] Error parsing message:', e);
                }
            };
            this.ws.onerror = () => {};
            this.ws.onclose = () => {};
        } catch (error) {
            console.error('[UI] Connection error:', error);
            alert('Failed to connect to table. Please try again.');
        }
    }


    handleMessage(data) {
        if (data.type === 'state') {
            this.lastState = data.data;
            this.debugState(data.data);
            this.updateTableState(data.data);
            if (data.version !== undefined) this.expectedVersion = data.version;
            
            // Auto-join if not already seated
            if (this.lastState && !this.lastState.seats?.some(s => s?.player_id === this.playerId)) {
                this.joinTable();
            }
        } else if (data.type === 'command_accepted') {
            console.log(`[UI] Command accepted: idempotency_key=${data.idempotency_key}, new_version=${data.new_version}`);
            if (data.new_version !== undefined) {
                this.expectedVersion = data.new_version;
            }
        } else if (data.type === 'error') {
            console.error(`[UI] Error from server: ${data.message}`);
            this.handleError({ message: data.message });
        } else {
            console.warn(`[UI] Unknown message type: ${data.type}`, data);
        }
    }


    updateTableState(state) {
        this.updatePlayersRow(state);
        this.updateCommunityCards(state.community_cards || []);
        this.updatePots(state.pots || []);
        this.updateYourCards(state);
        this.updatePlayerStack(state);
        this.updateActions(state);
    }
    
    updatePlayersRow(state) {
        if (!this.playersRow) return;
        
        this.playersRow.innerHTML = '';
        const seats = (state.seats || []).filter(s => s !== null);
        
        seats.forEach(seat => {
            const playerItem = document.createElement('div');
            playerItem.className = 'player-item';
            
            const isToAct = state.to_act_seat === seat.seat_id;
            const isActive = seat.status === 'ACTIVE' || seat.status === 'ALL_IN';
            const avatar = this.getAvatarEmoji(seat.player_id);
            const shortName = (seat.player_id || `Player${seat.seat_id + 1}`).replace('player_', '').substring(0, 10);
            const betBadge = seat.committed_total > 0 ? `<div class="player-bet">${seat.committed_total}</div>` : '';
            
            playerItem.innerHTML = `
                ${betBadge}
                <div class="player-avatar ${isActive ? 'active' : ''} ${isToAct ? 'to-act' : ''}">${avatar}</div>
                <div class="player-name">${shortName}</div>
                <div class="player-score">${seat.stack}</div>
            `;
            
            this.playersRow.appendChild(playerItem);
        });
    }
    
    updatePlayerStack(state) {
        const mySeat = state.seats?.find(s => s?.player_id === this.playerId);
        if (mySeat?.stack && this.playerStack) {
            this.playerStack.textContent = mySeat.stack.toLocaleString();
        }
    }
    
    updateActions(state) {
        const mySeat = state.seats?.find(s => s?.player_id === this.playerId);
        const street = state.street || 'WAITING';
        const isHandActive = street !== 'WAITING' && street !== 'COMPLETE';
        const canAct = isHandActive && mySeat && mySeat.status === 'ACTIVE' && state.to_act_seat === mySeat.seat_id;
        
        // Show start hand button if waiting and seated
        const seatedCount = state.seats.filter(s => s && s.player_id).length;
        const canStartHand = !isHandActive && mySeat && seatedCount >= 2;
        
        console.log(`[UI] updateActions: street=${street}, isHandActive=${isHandActive}, canAct=${canAct}, canStartHand=${canStartHand}, seatedCount=${seatedCount}, mySeat=${!!mySeat}`);
        
        if (canAct) {
            // Player's turn - show action panel
            this.currentSeat = mySeat.seat_id;
            if (this.actionPanel) {
                this.actionPanel.style.display = 'block';
                this.updateActionButtons(state, mySeat);
            }
            if (this.actionCenter) this.actionCenter.style.display = 'none';
        } else {
            // Not player's turn
            this.currentSeat = null;
            if (this.actionPanel) this.actionPanel.style.display = 'none';
            
            if (this.actionCenter) {
                this.actionCenter.style.display = 'flex';
                
                if (canStartHand) {
                    // Show start hand button
                    console.log('[UI] Showing start hand button');
                    if (this.startHandBtn) {
                        this.startHandBtn.style.display = 'block';
                        this.startHandBtn.disabled = false;
                    }
                    if (this.waitBtn) {
                        this.waitBtn.style.display = 'none';
                    }
                } else if (!isHandActive) {
                    // Show wait message
                    if (this.startHandBtn) {
                        this.startHandBtn.style.display = 'none';
                    }
                    if (this.waitBtn) {
                        this.waitBtn.style.display = 'block';
                        this.waitBtn.textContent = seatedCount < 2 ? 'Waiting for players...' : 'Wait for the next hand';
                        this.waitBtn.disabled = true;
                    }
                } else {
                    // Hand is active but not player's turn
                    if (this.startHandBtn) {
                        this.startHandBtn.style.display = 'none';
                    }
                    if (this.waitBtn) {
                        this.waitBtn.style.display = 'block';
                        this.waitBtn.textContent = 'Wait for your turn';
                        this.waitBtn.disabled = true;
                    }
                }
            }
        }
    }

    updateYourCards(state) {
        if (!this.yourCards) return;
        
        const mySeat = state.seats?.find(s => s && s.player_id === this.playerId);
        this.yourCards.innerHTML = '';
        
        if (mySeat?.hole_cards?.length === 2) {
            mySeat.hole_cards.forEach(card => {
                const cardEl = this.createCardElement(card);
                if (cardEl?.innerHTML?.trim()) {
                    this.yourCards.appendChild(cardEl);
                }
            });
        } else {
            for (let i = 0; i < 2; i++) {
                const cardBack = document.createElement('div');
                cardBack.className = 'card-back';
                this.yourCards.appendChild(cardBack);
            }
        }
    }

    updateCommunityCards(cards) {
        if (!this.communityCards) return;
        
        this.communityCards.innerHTML = '';
        if (!cards?.length) return;
        
        cards.forEach(card => {
            const cardEl = this.createCardElement(card);
            if (cardEl) this.communityCards.appendChild(cardEl);
        });
    }

    createCardElement(card) {
        if (typeof card !== 'object' || card === null) return null;
        
        const rankValue = typeof card.rank === 'object' && card.rank?.value !== undefined 
            ? card.rank.value 
            : typeof card.rank === 'number' 
                ? card.rank 
                : parseInt(card.rank?.value || card.rank?.name || card.rank);
        
        const suitValue = typeof card.suit === 'object' && card.suit?.value !== undefined
            ? card.suit.value
            : typeof card.suit === 'number'
                ? card.suit
                : parseInt(card.suit?.value || card.suit?.name || card.suit);
        
        if (typeof rankValue !== 'number' || isNaN(rankValue) || typeof suitValue !== 'number' || isNaN(suitValue)) {
            return null;
        }
        
        if (rankValue < 2 || rankValue > 14 || suitValue < 0 || suitValue > 3) {
            return null;
        }
        
        const cardEl = document.createElement('div');
        const rank = this.getRankSymbol(rankValue);
        const suit = this.getSuitSymbol(suitValue);
        const isRed = suitValue === 1 || suitValue === 2;
        
        cardEl.className = `card ${isRed ? 'red' : 'black'}`;
        cardEl.innerHTML = `
            <div class="card-rank">${rank}</div>
            <div class="card-suit">${suit}</div>
        `;
        
        return cardEl;
    }

    getRankSymbol(rank) {
        const ranks = { 2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8', 9: '9', 10: '10', 11: 'J', 12: 'Q', 13: 'K', 14: 'A' };
        return ranks[rank] || rank;
    }

    getSuitSymbol(suit) {
        const suits = { 0: '♣', 1: '♦', 2: '♥', 3: '♠' };
        return suits[suit] || suit;
    }

    updatePots(pots) {
        const totalPot = pots.reduce((sum, pot) => sum + (pot.amount || 0), 0);
        if (this.potValueEl) this.potValueEl.textContent = `$${totalPot}`;
        if (this.potDisplay) this.potDisplay.style.display = 'flex';
    }

    updateActionButtons(state, seat) {
        if (!this.actionInfo || !this.foldBtn || !this.checkBtn || !this.callBtn || !this.betBtn || !this.raiseBtn) return;
        
        const callAmount = Math.max(0, (state.current_bet || 0) - (seat.committed_street || 0));
        const minBet = state.big_blind || 100;
        const minRaiseIncrement = state.min_raise || state.big_blind || 100;
        const minRaiseTotal = callAmount + minRaiseIncrement;
        const hasBet = state.current_bet > 0;
        
        this.actionInfo.innerHTML = `
            <div style="font-size: 13px; margin-bottom: 8px;">
                <strong>Stack:</strong> ${seat.stack} · 
                <strong>Current Bet:</strong> ${state.current_bet || 0} · 
                <strong>To Call:</strong> ${callAmount}
            </div>
            <div style="font-size: 11px; color: var(--text-tertiary);">
                ${hasBet ? `Min Raise: ${minRaiseIncrement} (total: ${minRaiseTotal})` : `Min Bet: ${minBet}`}
            </div>
        `;
        
        this.foldBtn.disabled = callAmount === 0;
        this.checkBtn.disabled = callAmount > 0;
        this.callBtn.disabled = callAmount === 0 || seat.stack === 0;
        this.callBtn.textContent = callAmount > 0 ? `Call ${Math.min(callAmount, seat.stack)}` : 'Call';
        this.betBtn.disabled = hasBet || seat.stack === 0;
        this.raiseBtn.disabled = !hasBet || seat.stack === 0;
        
        if (this.betAmountInput) {
            if (hasBet) {
                this.betAmountInput.min = minRaiseTotal;
                this.betAmountInput.max = seat.stack;
                this.betAmountInput.placeholder = `Raise to (${minRaiseTotal}-${seat.stack})`;
                this.betAmountInput.value = minRaiseTotal;
            } else {
                this.betAmountInput.min = minBet;
                this.betAmountInput.max = seat.stack;
                this.betAmountInput.placeholder = `Bet (${minBet}-${seat.stack})`;
                this.betAmountInput.value = minBet;
            }
        }
    }

    async joinTable() {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }
        
        const state = this.lastState || this.getCurrentState();
        if (!state?.seats) {
            return;
        }
        
        // Already seated
        if (state.seats.some(s => s?.player_id === this.playerId)) {
            return;
        }
        
        // Check if table is full (6 players max)
        const seatedCount = state.seats.filter(s => s && s.player_id).length;
        if (seatedCount >= 6) {
            console.warn('[UI] Table is full (6 players max), redirecting to find new table');
            // Reconnect to find/create a new table
            this.connect();
            return;
        }
        
        const seatId = this.findNextAvailableSeat(state);
        if (seatId === null) {
            console.warn('[UI] No available seats');
            return;
        }
        
        console.log(`[UI] Joining table at seat ${seatId} with ${this.playerChips} chips`);
        this.sendCommand({
            type: 'sit_down',
            data: {
                seat_id: seatId,
                stack: this.playerChips,
                player_id: this.playerId
            },
            idempotency_key: `join-${this.playerId}-${Date.now()}`,
            expected_version: this.expectedVersion
        });
    }
    
    async loadPlayerChips() {
        try {
            const response = await fetch(`${this.baseUrl}/api/v1/players/me`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                this.playerChips = data.chips || 1000;
            }
        } catch (error) {
            console.error('[UI] Error loading player chips:', error);
            this.playerChips = 1000; // Default fallback
        }
    }
    
    

    async startHand() {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.error('[UI] WebSocket not connected');
            alert('Not connected to table. Please wait...');
            return;
        }
        const state = this.getCurrentState();
        if (!state) {
            console.error('[UI] No state available');
            return;
        }
        const seatedPlayers = state.seats.filter(s => s && s.player_id);
        if (seatedPlayers.length < 2) {
            alert('Need at least 2 players to start a hand');
            return;
        }
        
        // Generate hand_id and seed_commit
        const handId = `hand-${this.tableId}-${Date.now()}`;
        const seedCommit = `seed-${Date.now()}-${Math.random().toString(36).substring(7)}`;
        
        console.log(`[UI] Starting hand: ${handId}`);
        
        this.sendCommand({
            type: 'start_hand',
            data: {
                hand_id: handId,
                seed_commit: seedCommit
            },
            idempotency_key: `start-${Date.now()}`,
            expected_version: this.expectedVersion
        });
    }
    
    getCurrentState() {
        return this.lastState || { seats: Array(9).fill(null), street: 'WAITING', current_bet: 0, pots: [] };
    }
    
    findNextAvailableSeat(state) {
        const seats = state.seats || [];
        // Count seated players - max 6 per table
        const seatedCount = seats.filter(s => s && s.player_id).length;
        if (seatedCount >= 6) {
            console.log('[UI] Table is full (6 players max), should create new table');
            return null; // Table is full
        }
        
        // Find first empty seat (None/null) or seat with no player_id
        // Limit to 6 seats total (max 6 players per table)
        for (let i = 0; i < Math.min(6, seats.length || 6); i++) {
            const seat = seats[i];
            if (!seat || !seat.player_id) {
                return i;
            }
        }
        return null;
    }

    async act(actionType, amount = null) {
        if (!this.lastState || this.currentSeat === null) {
            alert('Not your turn or game state unavailable');
            return;
        }
        
        const mySeat = this.lastState.seats?.find(s => s?.player_id === this.playerId);
        if (!mySeat) return;
        
        this.sendCommand({
            type: 'act',
            data: {
                seat_id: mySeat.seat_id,
                action_type: actionType,
                amount: amount
            },
            idempotency_key: `act-${Date.now()}-${Math.random()}`,
            expected_version: this.expectedVersion
        });
    }
    
    call() {
        const mySeat = this.lastState?.seats?.find(s => s?.player_id === this.playerId);
        if (!mySeat) return;
        const callAmount = Math.max(0, (this.lastState.current_bet || 0) - (mySeat.committed_street || 0));
        if (callAmount === 0) {
            alert('No bet to call');
            return;
        }
        this.act('CALL', null);
    }
    
    bet() {
        const amount = this._getBetAmount();
        const mySeat = this.lastState?.seats?.find(s => s?.player_id === this.playerId);
        if (!amount || !mySeat || amount > mySeat.stack) {
            alert(`Bet exceeds your stack (${mySeat?.stack || 0})`);
            return;
        }
        const minBet = this.lastState.big_blind || 100;
        if (amount < minBet) {
            alert(`Bet must be at least ${minBet}`);
            return;
        }
        this.act('BET', amount);
    }
    
    raise() {
        const amount = this._getBetAmount();
        const mySeat = this.lastState?.seats?.find(s => s?.player_id === this.playerId);
        if (!amount || !mySeat || amount > mySeat.stack) {
            alert(`Raise exceeds your stack (${mySeat?.stack || 0})`);
            return;
        }
        const callAmount = Math.max(0, (this.lastState.current_bet || 0) - (mySeat.committed_street || 0));
        const minRaiseTotal = callAmount + (this.lastState.min_raise || this.lastState.big_blind || 100);
        if (amount < minRaiseTotal) {
            alert(`Raise must be at least ${minRaiseTotal}`);
            return;
        }
        this.act('RAISE', amount);
    }
    
    _getBetAmount() {
        if (!this.betAmountInput || !this.lastState) return null;
        const amount = parseInt(this.betAmountInput.value);
        if (isNaN(amount) || amount <= 0) {
            alert('Please enter a valid amount');
            return null;
        }
        return amount;
    }

    sendCommand(command) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            alert('Not connected to server');
            return;
        }
        this.ws.send(JSON.stringify(command));
    }
    
    handleError(error) {
        const message = error.message || error;
        if (message.includes('Need at least 2')) {
            alert('Need at least 2 players seated to start a hand');
        } else {
            alert('Error: ' + message);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.pokerUI = new PokerUI();
});

