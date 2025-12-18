import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'package:intl/intl.dart';
import 'package:google_fonts/google_fonts.dart';
import 'dart:async';

void main() {
  runApp(const CyberBarberApp());
}

// --- TEMA CYBERPUNK ---
class CyberTheme {
  static const Color black = Color(0xFF050505);
  static const Color darkGrey = Color(0xFF121212);
  static const Color neonYellow = Color(0xFFFFD700); // Amarillo Oro/Cyber
  static const Color neonRed = Color(0xFFFF2A2A);
  static const Color neonBlue = Color(0xFF00F0FF);
  
  static TextStyle get techFont => GoogleFonts.robotoMono();
}

class CyberBarberApp extends StatelessWidget {
  const CyberBarberApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Barber Admin Z',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: CyberTheme.black,
        primaryColor: CyberTheme.neonYellow,
        colorScheme: const ColorScheme.dark(
          primary: CyberTheme.neonYellow,
          secondary: CyberTheme.neonBlue,
          surface: CyberTheme.darkGrey,
        ),
        textTheme: GoogleFonts.robotoMonoTextTheme(Theme.of(context).textTheme).apply(
          bodyColor: Colors.white,
          displayColor: CyberTheme.neonYellow,
        ),
      ),
      home: const ServerConnectScreen(),
    );
  }
}

// === URL FIJA DEL SERVIDOR ===
const String SERVER_URL = "https://barberia-bot-production.up.railway.app";

// --- PANTALLA DE CONEXIÓN AL SERVIDOR ---
class ServerConnectScreen extends StatefulWidget {
  const ServerConnectScreen({super.key});

  @override
  State<ServerConnectScreen> createState() => _ServerConnectScreenState();
}

class _ServerConnectScreenState extends State<ServerConnectScreen> {
  bool _connecting = true;
  String _error = "";

  @override
  void initState() {
    super.initState();
    _autoConnect();
  }

  Future<void> _autoConnect() async {
    try {
      final dio = Dio();
      await dio.get('$SERVER_URL/api/stats', 
        options: Options(
          sendTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
        )
      );
      
      if (mounted) {
        Navigator.pushReplacement(
          context, 
          MaterialPageRoute(builder: (_) => HomeScreen(baseUrl: SERVER_URL)),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _connecting = false;
          _error = e.toString();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_connecting) {
      return Scaffold(
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.flash_on, size: 80, color: CyberTheme.neonYellow),
              const SizedBox(height: 20),
              Text("CONECTANDO...", style: TextStyle(color: CyberTheme.neonYellow, fontSize: 24)),
              const SizedBox(height: 20),
              const CircularProgressIndicator(color: CyberTheme.neonYellow),
            ],
          ),
        ),
      );
    }
    
    // Si hay error, mostrar botón para reintentar
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error, size: 80, color: Colors.red),
            const SizedBox(height: 20),
            Text("ERROR DE CONEXIÓN", style: TextStyle(color: Colors.red, fontSize: 24)),
            const SizedBox(height: 10),
            Padding(
              padding: const EdgeInsets.all(20),
              child: Text(_error, style: TextStyle(color: Colors.white70), textAlign: TextAlign.center),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: () {
                setState(() {
                  _connecting = true;
                  _error = "";
                });
                _autoConnect();
              },
              style: ElevatedButton.styleFrom(backgroundColor: CyberTheme.neonYellow),
              child: Text("REINTENTAR", style: TextStyle(color: Colors.black)),
            ),
          ],
        ),
      ),
    );
  }
}

// --- PANTALLA PRINCIPAL (DASHBOARD) ---
class HomeScreen extends StatefulWidget {
  final String baseUrl;
  const HomeScreen({super.key, required this.baseUrl});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentIndex = 0;
  late List<Widget> _screens;

  @override
  void initState() {
    super.initState();
    _screens = [
      DashboardTab(baseUrl: widget.baseUrl),
      AgendaTab(baseUrl: widget.baseUrl),
      ConfigTab(baseUrl: widget.baseUrl),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(child: _screens[_currentIndex]),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: CyberTheme.neonYellow, width: 2)),
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: (i) => setState(() => _currentIndex = i),
          backgroundColor: CyberTheme.black,
          selectedItemColor: CyberTheme.neonYellow,
          unselectedItemColor: Colors.grey,
          type: BottomNavigationBarType.fixed,
          items: const [
            BottomNavigationBarItem(icon: Icon(Icons.dashboard), label: 'STATS'),
            BottomNavigationBarItem(icon: Icon(Icons.calendar_month), label: 'AGENDA'),
            BottomNavigationBarItem(icon: Icon(Icons.settings_input_component), label: 'SYSTEM'),
          ],
        ),
      ),
    );
  }
}

// --- TAB 1: ESTADÍSTICAS ---
class DashboardTab extends StatefulWidget {
  final String baseUrl;
  const DashboardTab({super.key, required this.baseUrl});

  @override
  State<DashboardTab> createState() => _DashboardTabState();
}

class _DashboardTabState extends State<DashboardTab> {
  Map<String, dynamic>? stats;
  bool loading = true;
  bool botEncendido = true;

  @override
  void initState() {
    super.initState();
    _fetchStats();
  }

  Future<void> _fetchStats() async {
    try {
      final dio = Dio();
      final response = await dio.get('${widget.baseUrl}/api/stats',
        options: Options(
          sendTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
        )
      );
      if (mounted) {
        setState(() {
          stats = response.data;
          botEncendido = response.data['bot_encendido'] ?? true;
          loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => loading = false);
        print("Error fetching stats: $e");
      }
    }
  }

  Future<void> _toggleBot() async {
    try {
      final dio = Dio();
      await dio.post('${widget.baseUrl}/api/toggle_bot',
        data: {'encendido': !botEncendido},
        options: Options(
          sendTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
        )
      );
      if (mounted) {
        setState(() => botEncendido = !botEncendido);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(botEncendido ? "✅ BOT ENCENDIDO" : "⛔ BOT APAGADO"))
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("❌ ERROR: $e"))
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator(color: CyberTheme.neonYellow));

    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildHeader("STATUS REPORT"),
          const SizedBox(height: 20),
          // Toggle del Bot
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: botEncendido ? CyberTheme.neonBlue.withOpacity(0.2) : CyberTheme.neonRed.withOpacity(0.2),
              border: Border.all(color: botEncendido ? CyberTheme.neonBlue : CyberTheme.neonRed, width: 2),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text("BOT WHATSAPP", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                    const SizedBox(height: 5),
                    Text(
                      botEncendido ? "🟢 ENCENDIDO" : "🔴 APAGADO",
                      style: TextStyle(color: botEncendido ? CyberTheme.neonBlue : CyberTheme.neonRed, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
                Transform.scale(
                  scale: 1.5,
                  child: GestureDetector(
                    onTap: _toggleBot,
                    child: Container(
                      width: 60,
                      height: 35,
                      decoration: BoxDecoration(
                        color: botEncendido ? CyberTheme.neonBlue : Colors.grey,
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Stack(
                        children: [
                          AnimatedPositioned(
                            duration: const Duration(milliseconds: 300),
                            left: botEncendido ? 28 : 3,
                            top: 3,
                            child: Container(
                              width: 29,
                              height: 29,
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(15),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          Expanded(
            child: GridView.count(
              crossAxisCount: 2,
              crossAxisSpacing: 16,
              mainAxisSpacing: 16,
              children: [
                _buildStatCard("CITAS HOY", "${stats?['citas_hoy'] ?? 0}", Icons.cut),
                _buildStatCard("MENSAJES", "${stats?['mensajes_hoy'] ?? 0}", Icons.message),
                _buildStatCard("CHATS ACTIVOS", "${stats?['conversaciones_activas'] ?? 0}", Icons.people),
                _buildStatCard("SYSTEM", "ONLINE", Icons.check_circle, color: CyberTheme.neonBlue),
              ],
            ),
          ),
          CyberButton(text: "REFRESH DATA", onTap: _fetchStats),
        ],
      ),
    );
  }

  Widget _buildStatCard(String title, String value, IconData icon, {Color color = CyberTheme.neonYellow}) {
    return Container(
      decoration: BoxDecoration(
        color: CyberTheme.darkGrey,
        border: Border.all(color: color.withOpacity(0.5)),
        borderRadius: BorderRadius.zero, // Bordes rectos estilo cyberpunk
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 40, color: color),
          const SizedBox(height: 10),
          Text(value, style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: Colors.white)),
          Text(title, style: const TextStyle(color: Colors.grey, fontSize: 12)),
        ],
      ),
    );
  }
}

// --- TAB 2: AGENDA MEJORADA (CALENDARIO + SLOTS) ---
class AgendaTab extends StatefulWidget {
  final String baseUrl;
  const AgendaTab({super.key, required this.baseUrl});

  @override
  State<AgendaTab> createState() => _AgendaTabState();
}

class _AgendaTabState extends State<AgendaTab> {
  DateTime _selectedDate = DateTime.now();
  DateTime _focusedMonth = DateTime.now();
  List<dynamic> _citas = [];
  bool _loading = false;
  bool _showForm = false;
  bool _showCalendar = true; // Controla si se ve el calendario o los slots

  final TextEditingController _clienteCtrl = TextEditingController();
  final TextEditingController _horaCtrl = TextEditingController();
  final TextEditingController _telefonoCtrl = TextEditingController();
  final TextEditingController _servicioCtrl = TextEditingController();
  final TextEditingController _totalCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _fetchCitas();
  }

  Future<void> _fetchCitas() async {
    setState(() => _loading = true);
    try {
      final dio = Dio();
      String fechaStr = DateFormat('yyyy-MM-dd').format(_selectedDate);
      final response = await dio.get('${widget.baseUrl}/api/citas?fecha=$fechaStr',
        options: Options(
          sendTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
        )
      );
      if (mounted) {
        setState(() {
          _citas = response.data ?? [];
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _loading = false);
        print("Error fetching citas: $e");
      }
    }
  }

  Future<void> _crearCita() async {
    if (_clienteCtrl.text.isEmpty || _horaCtrl.text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("⚠️ Completa Cliente y Hora"))
      );
      return;
    }

    try {
      final dio = Dio();
      String fechaStr = DateFormat('yyyy-MM-dd').format(_selectedDate);
      await dio.post('${widget.baseUrl}/api/citas',
        data: {
          'fecha': fechaStr,
          'hora': _horaCtrl.text,
          'cliente_nombre': _clienteCtrl.text,
          'telefono': _telefonoCtrl.text,
          'servicio': _servicioCtrl.text.isEmpty ? 'Corte' : _servicioCtrl.text,
          'total': double.tryParse(_totalCtrl.text) ?? 0,
        },
        options: Options(
          sendTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
        )
      );
      
      if (mounted) {
        _clienteCtrl.clear();
        _horaCtrl.clear();
        _telefonoCtrl.clear();
        _servicioCtrl.clear();
        _totalCtrl.clear();
        setState(() => _showForm = false);
        _fetchCitas();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("✅ CITA CREADA"))
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("❌ ERROR: $e"))
        );
      }
    }
  }

  Future<void> _borrarCita(dynamic cita) async {
    try {
      final dio = Dio();
      await dio.delete('${widget.baseUrl}/api/citas/${cita['id']}',
        options: Options(
          sendTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
        )
      );
      
      if (mounted) {
        _fetchCitas();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("✅ CITA ELIMINADA"))
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("❌ ERROR: $e"))
        );
      }
    }
  }

  // --- CALENDAR GRID LOGIC ---
  List<Widget> _buildCalendarGrid() {
    List<Widget> gridItems = [];

    // Header Días de la semana
    List<String> weekDays = ['D', 'L', 'M', 'X', 'J', 'V', 'S'];
    for (var day in weekDays) {
      gridItems.add(Center(
        child: Text(day, style: const TextStyle(color: CyberTheme.neonBlue, fontWeight: FontWeight.bold, fontSize: 18)),
      ));
    }

    // Calcular días
    int year = _focusedMonth.year;
    int month = _focusedMonth.month;
    int daysInMonth = DateUtils.getDaysInMonth(year, month);
    DateTime firstDayOfMonth = DateTime(year, month, 1);
    int firstWeekday = firstDayOfMonth.weekday;

    // Ajuste para que Domingo sea 0 (DateTime usa Lun=1...Dom=7)
    // Pero en nuestra grid queremos Dom=0, Lun=1...
    // Si weekday es 7 (Domingo), en nuestra grid índice 0.
    // Si weekday es 1 (Lunes), en nuestra grid índice 1.
    int startingIndex = (firstWeekday % 7);

    // Espacios vacíos antes del primer día
    for (int i = 0; i < startingIndex; i++) {
      gridItems.add(Container());
    }

    // Días del mes
    for (int i = 1; i <= daysInMonth; i++) {
      DateTime date = DateTime(year, month, i);
      bool isSelected = DateUtils.isSameDay(date, _selectedDate);
      bool isToday = DateUtils.isSameDay(date, DateTime.now());
      bool isSunday = date.weekday == DateTime.sunday;

      gridItems.add(
        GestureDetector(
          onTap: () {
            if (!isSunday) {
              setState(() {
                _selectedDate = date;
                _showCalendar = false; // Ir a la vista de slots
                _fetchCitas();
              });
            }
          },
          child: Container(
            margin: const EdgeInsets.all(4),
            decoration: BoxDecoration(
              color: isSelected
                  ? CyberTheme.neonYellow
                  : (isToday ? CyberTheme.neonBlue.withOpacity(0.3) : CyberTheme.darkGrey),
              border: Border.all(
                color: isSelected ? CyberTheme.neonYellow : (isToday ? CyberTheme.neonBlue : Colors.transparent)
              ),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Center(
              child: Text(
                "$i",
                style: TextStyle(
                  color: isSelected
                    ? Colors.black
                    : (isSunday ? Colors.grey.withOpacity(0.3) : Colors.white),
                  fontWeight: FontWeight.bold,
                  decoration: isSunday ? TextDecoration.lineThrough : null,
                ),
              ),
            ),
          ),
        )
      );
    }
    return gridItems;
  }

  // Lógica Core de Slots
  List<Widget> _buildTimeSlots() {
    List<Widget> slots = [];
    
    // Configuración horario: 08:00 a 20:00 (Cierre a las 20:00, último turno 19:00)
    DateTime startTime = DateTime(_selectedDate.year, _selectedDate.month, _selectedDate.day, 8, 0);
    DateTime endTime = DateTime(_selectedDate.year, _selectedDate.month, _selectedDate.day, 20, 0);
    Duration step = const Duration(minutes: 60); // Slots de 1 hora

    DateTime current = startTime;

    while (current.isBefore(endTime)) {
      int hour = current.hour;
      
      // Regla de Descanso: 12:00 a 13:00 (No se muestra slot o se muestra deshabilitado)
      if (hour == 12) {
        slots.add(_buildRestSlot(current));
        current = current.add(step); 
        continue;
      }

      // Buscar si hay cita en este horario
      var cita = _citas.firstWhere(
        (c) => c['hora'].toString().startsWith(DateFormat('HH:mm').format(current)), 
        orElse: () => null
      );

      slots.add(_buildAppointmentSlot(current, cita));
      current = current.add(step);
    }
    return slots;
  }

  Widget _buildRestSlot(DateTime time) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(vertical: 15, horizontal: 10),
      decoration: BoxDecoration(
        color: Colors.black,
        border: Border.all(color: Colors.grey.withOpacity(0.3)),
        gradient: LinearGradient(
          colors: [Colors.black, Colors.grey.shade900],
          stops: const [0.0, 0.1],
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
        )
      ),
      child: Row(
        children: [
          Text(DateFormat('HH:mm').format(time), style: const TextStyle(color: Colors.grey, fontWeight: FontWeight.bold)),
          const SizedBox(width: 20),
          const Expanded(child: Text("/// ALMUERZO / BREAK ///", style: TextStyle(color: Colors.grey, letterSpacing: 2))),
        ],
      ),
    );
  }

  Widget _buildAppointmentSlot(DateTime time, dynamic cita) {
    bool isOccupied = cita != null;
    return GestureDetector(
      onTap: () {
        if (!isOccupied) {
          _horaCtrl.text = DateFormat('HH:mm').format(time);
          setState(() => _showForm = true);
        }
      },
      child: MouseRegion(
        cursor: isOccupied ? SystemMouseCursors.forbidden : SystemMouseCursors.click,
        child: Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: isOccupied ? CyberTheme.neonRed.withOpacity(0.1) : CyberTheme.darkGrey,
            border: Border(
              left: BorderSide(color: isOccupied ? CyberTheme.neonRed : CyberTheme.neonYellow, width: 4),
            ),
          ),
          child: Row(
            children: [
              Text(DateFormat('HH:mm').format(time), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              const SizedBox(width: 20),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isOccupied ? cita['cliente_nombre'].toString().toUpperCase() : "DISPONIBLE",
                      style: TextStyle(
                        color: isOccupied ? CyberTheme.neonRed : CyberTheme.neonYellow,
                        fontWeight: FontWeight.bold,
                        fontSize: 16
                      ),
                    ),
                    if (isOccupied)
                      Text("SERVICIO: ${cita['servicio']}", style: const TextStyle(fontSize: 12, color: Colors.grey)),
                  ],
                ),
              ),
              if (isOccupied) ...[
                GestureDetector(
                  onTap: () => _borrarCita(cita),
                  child: MouseRegion(
                    cursor: SystemMouseCursors.click,
                    child: const Icon(Icons.delete_outline, color: CyberTheme.neonRed, size: 20),
                  ),
                ),
                const SizedBox(width: 10),
                const Icon(Icons.lock, color: CyberTheme.neonRed, size: 18)
              ] else
                 const Icon(Icons.add_circle_outline, color: CyberTheme.neonYellow, size: 18)
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          _buildHeader("AGENDA CONTROL"),
          const SizedBox(height: 10),

          // --- HEADER DEL CALENDARIO / NAVEGACIÓN ---
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              if (_showCalendar) ...[
                 GestureDetector(
                  onTap: () => setState(() => _focusedMonth = DateTime(_focusedMonth.year, _focusedMonth.month - 1)),
                  child: const Icon(Icons.arrow_back_ios, color: CyberTheme.neonYellow),
                ),
                Text(DateFormat('MMMM yyyy').format(_focusedMonth).toUpperCase(), style: const TextStyle(fontSize: 20, letterSpacing: 2)),
                GestureDetector(
                  onTap: () => setState(() => _focusedMonth = DateTime(_focusedMonth.year, _focusedMonth.month + 1)),
                  child: const Icon(Icons.arrow_forward_ios, color: CyberTheme.neonYellow),
                ),
              ] else ...[
                 GestureDetector(
                  onTap: () => setState(() => _showCalendar = true),
                  child: Row(
                    children: const [
                      Icon(Icons.arrow_back, color: CyberTheme.neonBlue),
                      SizedBox(width: 5),
                      Text("VOLVER AL MES", style: TextStyle(color: CyberTheme.neonBlue)),
                    ],
                  ),
                ),
                Text(DateFormat('dd MMM').format(_selectedDate).toUpperCase(), style: const TextStyle(fontSize: 20, letterSpacing: 2)),
                const SizedBox(width: 80), // Spacer
              ]
            ],
          ),
          const SizedBox(height: 20),

          // --- CONTENIDO PRINCIPAL ---
          Expanded(
            child: _showCalendar
              ? GridView.count(
                  crossAxisCount: 7,
                  children: _buildCalendarGrid(),
                )
              : (_loading
                  ? const Center(child: CircularProgressIndicator(color: CyberTheme.neonYellow))
                  : ListView(children: _buildTimeSlots())
                ),
          ),

          const SizedBox(height: 10),

          // --- BOTÓN AGREGAR MANUAL (Solo en vista de slots) ---
          if (!_showCalendar && !_showForm)
            CyberButton(text: "+ AGREGAR CITA MANUAL", onTap: () => setState(() => _showForm = true)),

          if (_showForm && !_showCalendar)
            _buildFormAgregar(),
        ],
      ),
    );
  }

  Widget _buildFormAgregar() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: CyberTheme.darkGrey,
        border: Border.all(color: CyberTheme.neonYellow, width: 2),
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text("NUEVA CITA", style: TextStyle(color: CyberTheme.neonYellow, fontWeight: FontWeight.bold, fontSize: 16)),
            const SizedBox(height: 12),
            _buildInputField("CLIENTE", _clienteCtrl),
            const SizedBox(height: 10),
            _buildInputField("HORA (HH:mm)", _horaCtrl),
            const SizedBox(height: 10),
            _buildInputField("TELÉFONO", _telefonoCtrl),
            const SizedBox(height: 10),
            _buildInputField("SERVICIO", _servicioCtrl),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: CyberButton(text: "CREAR", onTap: _crearCita),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: GestureDetector(
                    onTap: () => setState(() => _showForm = false),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 15),
                      decoration: BoxDecoration(
                        color: Colors.grey,
                        boxShadow: [
                          BoxShadow(color: Colors.grey.withOpacity(0.4), blurRadius: 10, spreadRadius: 1)
                        ],
                      ),
                      child: const Center(
                        child: Text("CANCELAR", style: TextStyle(color: Colors.black, fontWeight: FontWeight.bold, letterSpacing: 1.5, fontSize: 16)),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInputField(String label, TextEditingController ctrl) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: CyberTheme.neonBlue, fontSize: 11)),
        const SizedBox(height: 5),
        TextField(
          controller: ctrl,
          style: const TextStyle(color: Colors.white, fontSize: 14),
          decoration: const InputDecoration(
            filled: true,
            fillColor: Color(0xFF1A1A1A),
            enabledBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.grey)),
            focusedBorder: OutlineInputBorder(borderSide: BorderSide(color: CyberTheme.neonYellow)),
            contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          ),
        ),
      ],
    );
  }
}

// --- TAB 3: CONFIGURACIÓN (EDITAR VARIABLES) ---
class ConfigTab extends StatefulWidget {
  final String baseUrl;
  const ConfigTab({super.key, required this.baseUrl});

  @override
  State<ConfigTab> createState() => _ConfigTabState();
}

class _ConfigTabState extends State<ConfigTab> {
  final TextEditingController _nameCtrl = TextEditingController();
  final TextEditingController _instruccionesCtrl = TextEditingController();
  final TextEditingController _apiKeyCtrl = TextEditingController();
  bool loading = true;

  @override
  void initState() {
    super.initState();
    _loadConfig();
  }

  Future<void> _loadConfig() async {
    try {
      final dio = Dio();
      final response = await dio.get('${widget.baseUrl}/api/config',
        options: Options(
          sendTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
        )
      );
      var data = response.data;
      if (mounted) {
        setState(() {
          _nameCtrl.text = data['nombre_negocio'] ?? '';
          _instruccionesCtrl.text = data['instrucciones'] ?? '';
          _apiKeyCtrl.text = data['api_key'] ?? '';
          loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => loading = false);
        print("Error loading config: $e");
      }
    }
  }

  Future<void> _saveConfig() async {
    try {
      final dio = Dio();
      await dio.post('${widget.baseUrl}/api/config',
        data: {
          'nombre_negocio': _nameCtrl.text,
          'instrucciones': _instruccionesCtrl.text,
          'api_key': _apiKeyCtrl.text,
        },
        options: Options(
          sendTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
        )
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("✅ CONFIG UPLOADED SUCCESSFULLY"))
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("❌ UPLOAD FAILED: $e"))
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator(color: CyberTheme.neonYellow));

    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildHeader("SYSTEM CONFIG"),
            const SizedBox(height: 20),
            _buildCyberField("BUSINESS NAME", _nameCtrl),
            const SizedBox(height: 20),
            _buildCyberField("INSTRUCCIONES BOT (PROMPT)", _instruccionesCtrl, maxLines: 5),
            const SizedBox(height: 20),
            _buildCyberField("GEMINI API KEY", _apiKeyCtrl, obscure: true),
            const SizedBox(height: 40),
            CyberButton(text: "UPLOAD CONFIG", onTap: _saveConfig),
          ],
        ),
      ),
    );
  }

  Widget _buildCyberField(String label, TextEditingController ctrl, {int maxLines = 1, bool obscure = false}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: CyberTheme.neonBlue, fontSize: 12)),
        const SizedBox(height: 5),
        TextField(
          controller: ctrl,
          maxLines: maxLines,
          obscureText: obscure,
          style: const TextStyle(color: Colors.white),
          decoration: const InputDecoration(
            filled: true,
            fillColor: Color(0xFF1A1A1A),
            enabledBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.grey)),
            focusedBorder: OutlineInputBorder(borderSide: BorderSide(color: CyberTheme.neonYellow)),
          ),
        ),
      ],
    );
  }
}

// --- WIDGETS COMUNES ---
Widget _buildHeader(String title) {
  return Container(
    padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
    decoration: const BoxDecoration(
      border: Border(left: BorderSide(color: CyberTheme.neonYellow, width: 4)),
    ),
    child: Text(
      title,
      style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold, letterSpacing: 2, color: Colors.white),
    ),
  );
}

class CyberButton extends StatefulWidget {
  final String text;
  final VoidCallback onTap;

  const CyberButton({super.key, required this.text, required this.onTap});

  @override
  State<CyberButton> createState() => _CyberButtonState();
}

class _CyberButtonState extends State<CyberButton> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: widget.onTap,
        child: Transform.scale(
          scale: _isHovered ? 1.05 : 1.0,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 15),
            decoration: BoxDecoration(
              color: _isHovered ? CyberTheme.neonYellow.withOpacity(0.9) : CyberTheme.neonYellow,
              boxShadow: [
                BoxShadow(
                  color: CyberTheme.neonYellow.withOpacity(_isHovered ? 0.8 : 0.4),
                  blurRadius: _isHovered ? 20 : 10,
                  spreadRadius: _isHovered ? 2 : 1
                )
              ],
            ),
            child: Center(
              child: Text(
                widget.text,
                style: const TextStyle(color: Colors.black, fontWeight: FontWeight.bold, letterSpacing: 1.5, fontSize: 16),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
