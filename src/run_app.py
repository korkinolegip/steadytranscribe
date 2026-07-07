"""Входная точка для PyInstaller."""
import multiprocessing

if __name__ == "__main__":
    # КРИТИЧНО для собранного exe: без этого любой вызов multiprocessing/подпроцесса
    # с sys.executable запускает НОВУЮ копию приложения → окна плодятся бесконечно.
    multiprocessing.freeze_support()

    from steadytranscribe.app import main
    main()
