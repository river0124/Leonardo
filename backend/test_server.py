import FinanceDataReader as fdr

start_date = "2024-06-01"
hist = fdr.DataReader("005930", start_date)
print(hist.tail())