#!/usr/bin/env python
# coding: utf-8
# **Abstract:**
# ARIMAX is used to benchmark the results obtained by LSTM. The best result
# for daily temperature prediction is a MAE of 1.25 degrees for the city of
# Amsterdam. As exogenous components, the temperatures in 30 neighbouring
# cities are used, lagged by one day. Without exogoneous components the best
# MAE is around 1.47 degrees (note that this result fluctuates). Calculations
# can be sped up by resampling. ARIMAX is not really suited to work with
# patterns on a fine [time scale]
# (https://stackoverflow.com/questions/63438979/python-pmdarima-autoarima-does-not-work-with-large-data).
# It is mainly used here as benchmark. Calculations can be done on a laptop if
# seasonality is disabled. I used a [p3.2xlarge]
# (https://aws.amazon.com/ec2/instance-types/p3/)
# from AWS but did not get better results with seasonality turned on.
# PMDArima can not exploit the GPUs, so using an instance with GPU does not
# add that much value.

# settings
import pmdarima as pm
import numpy as np
import statsmodels.api as sm
from sklearn.model_selection import train_test_split

import temp
cities = 30  # neighbouring cities to include in exogenous component of ARMAX
test_size = 0.2

df = temp.read_data(option='daily')

# For simplicity, I start out by predicting the temperature in a single city;
# Amsterdam

df_city = (df.droplevel(level=['region', 'country'])
             .unstack(level='date').T.sort_index()
           )
df_city.Amsterdam.head()

# Let's assume heat is mostly transported by diffusion (Fick's law). Under
# this assumption the most correlating temperatures should be neighbouring
#  towns. The temperature in these town can be used as exogenous component.
# I compute the cross correlation matrix and grab the 5 most correlating
# components. The model is developed with respect to the errors
# so the coefficients have the usual interprestation see
# [Hyndman](https://robjhyndman.com/hyndsight/arimax/).

df_cor = df_city.corr()
df_cor.head()
# The top most correlating temperatures for the city of Amsterdam
top_cities = (
    df_cor[df_cor.index
           == 'Amsterdam'].T.nlargest(cities+1, ['Amsterdam'])
                          .index[0:cities+1]
                          .to_list()
             )
print(top_cities[1:])

# The results above make sense. Brussels is closer to Amsterdam than Paris.
#  There is a sea between London and Amsterdam.
# The exogenous components are computed via a shift.

df_data = (df_city[top_cities[1:]].shift(1)
                                  .assign(Amsterdam=df_city.Amsterdam)
                                  .dropna()
           )
df_data.head()

# Let's try to look for a weak overall trend. This trends only appears if
# sampled at a daily basis. I arrive at a global warming rate of 0.35 degrees
#  for the city of Amsterdam per decade.
# This seems to be in line with [literature]
# (https://www.climate.gov/news-features/understanding-climate/
#  climate-change-global-temperature), which predicts 0.18 degrees since 1980.
#  Note that the final model does not use this trend or is aware of it :-).

X = sm.add_constant(np.arange(len(df_city.Amsterdam)))
model = sm.OLS(df_city.Amsterdam.to_numpy(), X)
results = model.fit()
print(results.summary())
# this should be only significant for the daily case
if results.pvalues[1] < 0.05:
    print(f"Per decade \
           the temperature rises with {results.params[1]*365*10:.2f} degrees")

# For a fair comparison with a LSTM network,  let's do a train test split.
# Shuffle is disabled as ARMAX cannot fit on shuffled values.


train, test = train_test_split(df_data, test_size=test_size, shuffle=False)

# As a simple model, I use an ARIMA model without exogenous components.
# The parameters are explained in
# [tips and trick](https://alkaline-ml.com/pmdarima/tips_and_tricks.html) of
#  the ARIMA package. The AutoARIMA parameters are explained
#  [here](https://alkaline-ml.com/pmdarima/modules/generated/pmdarima.arima.AutoARIMA.html).
# It is possible to fit a weak trend to it, which could be interpreted
#  as global warming.
# This does not improve results

defaults = {
              'test': 'adf',     # use adftest to find optimal 'd'
              'trend': 'c',      # linear trend does not add value
                                 # use 't' for linear trend with time
              # (https://www.statsmodels.org/dev/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html#statsmodels.tsa.statespace.sarimax.SARIMAX)
              # seasonal settings
              'm': 1,
              # m observations per seasonal cycle, do not use larger
              #  numbers than 52 (takes too long too compute)
              'max_P': 3,
              'max_Q': 2,
              'D': 0,
              'seasonal': False,
              # Seasonality, temperature is highly seasonal, does not add value
              # regular settings
              'd': 0,
              'max_p': 6,
              'max_q': 4,
              'trace': True,
              'scoring': 'mae',    # mae for similiraty with RNN network
              'error_action': 'ignore',
              'suppress_warnings': True,
              'n_jobs': 1,         # Jobs in parallel, requires stepwise False
              'stepwise': True
            }
model = pm.auto_arima(train.Amsterdam, **defaults)
model.summary()

# Let's add the test data to the model but we do not update the parameters,
#  so it shouldn't use test data.

model.update(test.Amsterdam, maxiter=0)
_, test_resid = train_test_split(model.resid(), test_size=test_size,
                                 shuffle=False)
print(f"The MAE equals {np.mean(np.abs(test_resid)):.2f}")

# The model is fitted but now with the exogenous components.

model_exog = pm.auto_arima(train.Amsterdam, exogenous=train[top_cities[1:]],
                           **defaults)
model_exog.summary()

# The MAE is computed by adding the test set and not
#  updating the train results.

model_exog.update(test.Amsterdam, exogenous=test[top_cities[1:]], maxiter=0)
_, test_resid = train_test_split(model_exog.resid(), test_size=test_size,
                                 shuffle=False)
print(f"The MAE equals {np.mean(np.abs(test_resid)):.2f}")
