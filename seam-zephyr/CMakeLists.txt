cmake_minimum_required(VERSION 3.20)

if(CONFIG_SEAM)
  zephyr_library_named(seam)

  zephyr_library_include_directories(include)

  zephyr_library_sources(
    src/codec.c
    src/sampler.c
  )

  if(CONFIG_SEAM_TRANSPORT_USB_CDC)
    zephyr_library_sources(src/transport/usb_cdc.c)
  endif()

  if(CONFIG_SEAM_TRANSPORT_BLE_NUS)
    zephyr_library_sources(src/transport/ble_nus.c)
  endif()
endif()
