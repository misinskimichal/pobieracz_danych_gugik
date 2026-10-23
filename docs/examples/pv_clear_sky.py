"""PV illustration for a cloud-free day; not an annual energy yield forecast."""
import pandas as pd
import pvlib


def clear_sky_example():
    site = pvlib.location.Location(52.0, 21.0, tz='Europe/Warsaw', altitude=110)
    times = pd.date_range('2026-06-21', periods=96, freq='15min', tz=site.tz)
    sun = site.get_solarposition(times)
    sky = site.get_clearsky(times)
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=30, surface_azimuth=180,
        solar_zenith=sun['apparent_zenith'], solar_azimuth=sun['azimuth'],
        dni=sky['dni'], ghi=sky['ghi'], dhi=sky['dhi'])
    # An illustrative constant efficiency factor; no temperature/shading/snow model.
    power_kw = 10.0 * poa['poa_global'].fillna(0) / 1000 * 0.85
    return pd.DataFrame({'poa_W_m2': poa['poa_global'], 'illustrative_power_kW': power_kw})


if __name__ == '__main__':
    result = clear_sky_example()
    result.to_csv('pv_bezchmurny_dzien.csv')
    print('Ilustracyjna energia 10 kWp [kWh]:', result['illustrative_power_kW'].sum() * 0.25)
