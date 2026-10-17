def moving_average(samples, window):
    return [sum(samples[i-window+1:i+1]) / window for i in range(window-1, len(samples))]
