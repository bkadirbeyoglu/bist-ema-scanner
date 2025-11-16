# Backtest Results Interpretation Guide

## Performance Metrics Explained

### Total Return
**What it is:** Percentage gain/loss of portfolio
**Formula:** ((Final Value - Initial Value) / Initial Value) × 100

**Interpretation:**
- Positive = Profitable strategy
- Compare to buy-and-hold benchmark
- Consider time period (10% in 1 month vs 1 year)

**Example:**
- Started with $100,000
- Ended with $110,000
- Total Return = 10%

### Sharpe Ratio
**What it is:** Risk-adjusted return metric
**Formula:** (Return - Risk-Free Rate) / Standard Deviation of Returns

**Interpretation:**
- > 1.0 = Good (returns exceed risk taken)
- > 2.0 = Very Good
- > 3.0 = Excellent
- < 1.0 = Poor (not compensated for risk)

**Example:**
- Sharpe 0.5 = Barely beating risk-free returns
- Sharpe 2.0 = Earning good returns for risk taken
- Sharpe 3.5 = Exceptional risk-adjusted performance

**Important:** Only compare Sharpe ratios for same time periods!

### Maximum Drawdown
**What it is:** Largest peak-to-trough decline
**How calculated:** Largest percentage drop from any peak to subsequent trough

**Interpretation:**
- Shows worst-case scenario
- Indicates capital you could lose
- Important for risk management

**Example:**
- Portfolio peaked at $120,000
- Dropped to $100,000
- Max Drawdown = 16.7%

**Rule of Thumb:**
- < 10% = Conservative strategy
- 10-20% = Moderate risk
- > 20% = Aggressive strategy
- > 30% = Very high risk

### Win Rate
**What it is:** Percentage of profitable trades
**Formula:** (Winning Trades / Total Trades) × 100

**Interpretation:**
- Higher is generally better BUT...
- Must consider average win vs average loss
- 40% win rate with 3:1 reward:risk beats 60% with 1:2

**Example:**
- 100 total trades
- 55 winners, 45 losers
- Win Rate = 55%

### Profit Factor
**What it is:** Ratio of gross profits to gross losses
**Formula:** Total Profit from Wins / Total Loss from Losses

**Interpretation:**
- > 1.0 = Profitable (required minimum)
- 1.5-2.0 = Good
- > 2.0 = Excellent
- < 1.0 = Losing strategy

**Example:**
- Won $50,000 across all winning trades
- Lost $25,000 across all losing trades
- Profit Factor = 2.0 (made $2 for every $1 lost)

### Average Win / Average Loss
**What they are:** Mean profit per winning trade, mean loss per losing trade

**Interpretation:**
- Compare the ratio
- Ideal: Avg Win > Avg Loss
- If Avg Loss > Avg Win, need high win rate to profit

**Example Scenarios:**

**Scenario A (Good):**
- Avg Win: $500
- Avg Loss: $200
- Ratio: 2.5:1 (can win even with 40% win rate)

**Scenario B (Risky):**
- Avg Win: $200
- Avg Loss: $500
- Ratio: 1:2.5 (need >70% win rate to profit)

## Assessing Strategy Quality

### Excellent Strategy
- Total Return: >15% annually
- Sharpe Ratio: >2.0
- Max Drawdown: <15%
- Profit Factor: >2.0
- Win Rate: >50%

### Good Strategy
- Total Return: 8-15% annually
- Sharpe Ratio: 1.0-2.0
- Max Drawdown: 15-25%
- Profit Factor: 1.5-2.0
- Win Rate: 45-50%

### Needs Improvement
- Total Return: 0-8% annually
- Sharpe Ratio: 0.5-1.0
- Max Drawdown: 25-35%
- Profit Factor: 1.0-1.5
- Win Rate: 40-45%

### Not Viable
- Total Return: <0%
- Sharpe Ratio: <0.5
- Max Drawdown: >35%
- Profit Factor: <1.0
- Win Rate: <40%

## Common Pitfalls

### Overfitting
**Problem:** Strategy works perfectly on backtest, fails in live trading
**Cause:** Optimized for historical data, doesn't generalize
**Solution:**
- Use out-of-sample testing
- Keep strategy simple
- Avoid excessive parameters
- Test on multiple time periods

### Survivorship Bias
**Problem:** Only testing on stocks that survived
**Cause:** Missing delisted/bankrupt companies
**Solution:**
- Use survivorship-bias-free datasets
- Include delisted stocks
- Test on index constituents at time

### Look-Ahead Bias
**Problem:** Using future information
**Cause:** Indicators calculated with future data
**Solution:**
- Ensure all data point-in-time
- Rebalance on close, execute next day
- Check indicator calculations

### Transaction Costs
**Problem:** Ignoring commissions and slippage
**Reality:** Erodes returns, especially for high-frequency strategies
**Solution:**
- Include realistic commission (0.1% per trade)
- Add slippage (0.05-0.1%)
- Factor in spread for illiquid stocks

## Making Trading Decisions

### Question 1: Is this strategy profitable?
**Check:** Total Return > 0, Profit Factor > 1.0
**Answer:**
- YES: Proceed to next questions
- NO: Revise strategy or abandon

### Question 2: Is the return worth the risk?
**Check:** Sharpe Ratio, Max Drawdown
**Answer:**
- Sharpe > 1.0 AND Drawdown acceptable: YES
- Otherwise: Improve risk management

### Question 3: Is the strategy consistent?
**Check:** Trade distribution, monthly returns
**Answer:**
- Steady equity curve: YES
- Erratic with few big wins: RISKY
- Long flat periods: May need patience

### Question 4: Can I psychologically handle this?
**Check:** Max Drawdown, Avg Loss
**Answer:**
- If Max Drawdown = 30%, can you stomach 30% loss?
- If Avg Loss = $500, comfortable with that?
- Be honest - paper profits mean nothing if you can't execute

### Question 5: Does it beat buy-and-hold?
**Check:** Compare return to simply holding the asset
**Answer:**
- If strategy returns 8% but buy-and-hold returns 12%: FAIL
- Must outperform after accounting for effort and risk

## Final Checklist Before Live Trading

- [ ] Tested on multiple time periods
- [ ] Tested on multiple symbols
- [ ] Included realistic transaction costs
- [ ] Maximum drawdown acceptable
- [ ] Sharpe ratio >1.0
- [ ] Profit factor >1.5
- [ ] Understanding of why strategy works
- [ ] Psychological preparation for drawdowns
- [ ] Position sizing plan defined
- [ ] Risk management rules established
- [ ] Exit plan if strategy stops working

**Remember:** Past performance does not guarantee future results. Always start with small position sizes and increase gradually as strategy proves itself in live markets.